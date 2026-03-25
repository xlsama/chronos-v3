import { ofetch } from "ofetch";

export function transcribeAudio(blob: Blob): Promise<{ text: string }> {
  const formData = new FormData();
  formData.append("file", blob, "recording.webm");
  return ofetch<{ text: string }>("/api/asr/transcribe", {
    method: "POST",
    body: formData,
  });
}
