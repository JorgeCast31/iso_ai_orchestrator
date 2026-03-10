import anthropic
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL


class ClaudeClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = CLAUDE_MODEL
        #print("DEBUG Claude model:", self.model)

    def generate(self, prompt: str, max_tokens: int = 4000) -> str:
        #print("DEBUG sending model:", self.model)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)

        return "\n".join(parts).strip()