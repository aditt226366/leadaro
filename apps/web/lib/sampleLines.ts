/**
 * Preview lines, per language.
 *
 * Cartesia's `language` parameter selects pronunciation rules — it does NOT
 * translate. Feeding English text to a Hindi voice produces English words in a
 * Hindi accent, which is what made every language sound the same. The text has
 * to already be in the target language.
 *
 * Each line is the same script beat — greeting, AI disclosure, ask for thirty
 * seconds — so voices stay comparable across languages.
 */
export const SAMPLE_LINES: Record<string, string> = {
  en: "Hi, this is Emma from Leadaro. I'm an AI assistant. Do you have thirty seconds?",
  hi: "नमस्ते, मैं लीडारो से एम्मा बोल रही हूँ। मैं एक AI सहायक हूँ। क्या आपके पास तीस सेकंड हैं?",
  es: "Hola, soy Emma de Leadaro. Soy un asistente de inteligencia artificial. ¿Tiene treinta segundos?",
  fr: "Bonjour, je suis Emma de Leadaro. Je suis un assistant IA. Avez-vous trente secondes ?",
  de: "Hallo, hier ist Emma von Leadaro. Ich bin eine KI-Assistentin. Haben Sie dreißig Sekunden?",
  ar: "مرحبًا، أنا إيما من ليدارو. أنا مساعد ذكاء اصطناعي. هل لديك ثلاثون ثانية؟",
  ta: "வணக்கம், நான் லீடாரோவிலிருந்து எம்மா பேசுகிறேன். நான் ஒரு AI உதவியாளர். உங்களுக்கு முப்பது வினாடிகள் இருக்கிறதா?",
  te: "నమస్కారం, నేను లీడారో నుండి ఎమ్మా మాట్లాడుతున్నాను. నేను ఒక AI సహాయకురాలిని. మీకు ముప్పై సెకన్లు ఉన్నాయా?",
  ml: "നമസ്കാരം, ഞാൻ ലീഡാരോയിൽ നിന്നുള്ള എമ്മയാണ്. ഞാൻ ഒരു AI സഹായിയാണ്. നിങ്ങൾക്ക് മുപ്പത് സെക്കൻഡ് ഉണ്ടോ?",
  ja: "こんにちは、リーダロのエマです。私はAIアシスタントです。30秒ほどお時間よろしいですか？",
  zh: "您好，我是 Leadaro 的 Emma。我是一位人工智能助手。您有三十秒时间吗？",
  pt: "Olá, aqui é a Emma da Leadaro. Sou uma assistente de IA. Tem trinta segundos?",
  it: "Salve, sono Emma di Leadaro. Sono un'assistente AI. Ha trenta secondi?",
};

export const sampleLine = (lang?: string) =>
  SAMPLE_LINES[lang ?? "en"] ?? SAMPLE_LINES.en;

/** Languages whose script runs right-to-left, for correct input rendering. */
export const RTL = new Set(["ar", "he", "fa", "ur"]);
