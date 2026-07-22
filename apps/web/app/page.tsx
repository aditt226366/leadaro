import { redirect } from "next/navigation";
import { cookies } from "next/headers";

export default async function Root() {
  // Remember which surface the user was last on; default to Voice Outreach.
  const mode = (await cookies()).get("mode")?.value;
  redirect(mode === "call" ? "/call" : "/voice");
}
