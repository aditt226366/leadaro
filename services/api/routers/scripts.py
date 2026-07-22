"""Feature 1 — AI Script Generator (write / generate / import) + AI improvements."""
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

import llm
from auth import Principal, current_user
from schemas import ScriptGenerateIn, ScriptImproveIn

router = APIRouter(prefix="/scripts", tags=["scripts"])

GOAL_TEXT = {
    "book_meeting": "book a meeting or demo",
    "qualify_lead": "qualify whether the lead is a fit",
    "follow_up": "follow up on a prior conversation",
    "collect_payment": "remind the customer about an outstanding payment",
    "survey": "collect survey or feedback responses",
    "reengage": "re-engage a cold lead",
    "confirm_verify": "confirm or verify an appointment or detail",
}

SYSTEM = """You write scripts for AI voice agents that make outbound phone calls.

Hard rules, because this is spoken aloud on a live call:
- Every line must sound natural read aloud. No bullet points, no markdown, no emoji.
- Sentences must be short. A caller cannot re-read a long sentence.
- The greeting must include an AI disclosure — the person has a right to know
  they are speaking with an automated system. Keep it brief and unapologetic.
- Use {{variable}} placeholders for personalisation. Only use variables from the
  supplied list. Never invent a variable.
- Objection handling must acknowledge the objection before responding to it.
- Never promise pricing, legal, medical or financial outcomes.
- Aim for a two to three minute call at a natural speaking pace."""

VARIABLES = [
    "first_name", "last_name", "company", "industry", "designation",
    "city", "website", "meeting_link", "discount", "campaign_name", "product",
]


class GeneratedScript(BaseModel):
    """Mirrors the FRD §5 step 4 script section list."""
    greeting: str
    introduction: str
    pain_point: str
    offer: str
    cta: str
    objection_handling: str
    closing_statement: str
    thank_you: str
    voicemail_message: str
    fallback_script: str
    transfer_script: str
    estimated_duration_seconds: int


@router.post("/generate", response_model=GeneratedScript)
async def generate(body: ScriptGenerateIn, user: Principal = Depends(current_user)):
    """'Generate with AI' — prompt + website + goal + offer + tone → full script."""
    prompt = f"""Write a complete outbound call script.

Goal: {GOAL_TEXT[body.goal]}
What we offer: {body.offer}
Target audience: {body.audience or "business decision makers"}
Tone: {body.tone}
Desired call to action: {body.cta or "agree to a short follow-up meeting"}
Length: {body.length}
Language: {body.language}
Company website for context: {body.company_website or "not supplied"}
Extra instructions: {body.prompt or "none"}

Available variables (use only these): {", ".join("{{" + v + "}}" for v in VARIABLES)}

Fill every section. voicemail_message must work as a standalone 20-second
message. fallback_script is what the agent says when it cannot understand the
caller. transfer_script is what it says immediately before handing to a human."""

    try:
        return await llm.complete(SYSTEM, prompt, max_tokens=3000,
                                  output_format=GeneratedScript)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"generation failed: {e}")


@router.post("/improve")
async def improve(body: ScriptImproveIn, user: Principal = Depends(current_user)):
    """AI improvements: rewrite / shorten / retone."""
    instruction = {
        "rewrite": "Rewrite this to be clearer and more natural when spoken aloud.",
        "shorten": "Cut this to roughly half the length. Keep every concrete fact.",
        "professional": "Rewrite in a polished, business-professional register.",
        "friendly": "Rewrite in a warm, conversational register.",
        "urgent": "Rewrite to convey time sensitivity without pressuring or alarming.",
        "funny": "Rewrite with light, tasteful humour. Keep it professional.",
        "luxury": "Rewrite in an understated, premium register.",
        "sales": "Rewrite with a stronger, more confident close.",
        "support": "Rewrite in a patient, helpful customer-support register.",
        "recruitment": "Rewrite as a recruiter approaching a passive candidate.",
    }[body.action]

    text = await llm.complete(
        SYSTEM,
        f"{instruction}\n\nPreserve all {{{{variable}}}} placeholders exactly.\n"
        f"Return only the rewritten text.\n\n---\n{body.text}",
        max_tokens=1500,
    )
    return {"text": text.strip()}


@router.post("/import")
async def import_script(
    file: UploadFile = File(...), user: Principal = Depends(current_user),
):
    """'Import script' — .txt, .docx or .pdf."""
    name = (file.filename or "").lower()
    raw = await file.read()

    if name.endswith(".txt") or name.endswith(".md"):
        text = raw.decode("utf-8", errors="replace")
    elif name.endswith(".docx"):
        text = _docx_text(raw)
    elif name.endswith(".pdf"):
        text = _pdf_text(raw)
    else:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "supported formats: .txt, .md, .docx, .pdf",
        )

    if not text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "no readable text found in file")
    return {"text": text.strip(), "characters": len(text)}


def _docx_text(raw: bytes) -> str:
    """A .docx is a zip of XML — no library needed for plain paragraph text."""
    import re
    import zipfile

    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    # Paragraph breaks first, then strip every remaining tag.
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "PDF import needs `pip install pypdf`",
        )
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in reader.pages)
