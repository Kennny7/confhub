from openai import AsyncOpenAI

from meetbridge.config import Settings


class LocalLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.llm_base_url.strip() and settings.llm_model.strip())
        self.model_name = settings.llm_model
        self.client = (
            AsyncOpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key or "not-required-for-local-server",
                timeout=90.0,
            )
            if self.enabled
            else None
        )

    async def summarise_transcript(self, meeting_title: str, transcript: str) -> str:
        if not self.enabled or self.client is None:
            raise RuntimeError("LLM summarization is disabled; configure LLM_BASE_URL and LLM_MODEL")

        response = await self.client.chat.completions.create(
            model=self.model_name,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise meeting-notes assistant. Do not invent facts, owners, "
                        "deadlines, decisions, or commitments. Distinguish explicit decisions from "
                        "open questions. Return Markdown with sections: Executive summary, "
                        "Decisions, Action items (owner and due date only when stated), Risks, "
                        "Open questions. Mark missing information as Not specified."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Meeting: {meeting_title}\n\nTranscript:\n{transcript}",
                },
            ],
        )
        summary = response.choices[0].message.content
        if not summary:
            raise RuntimeError("The configured LLM returned an empty response")
        return summary
