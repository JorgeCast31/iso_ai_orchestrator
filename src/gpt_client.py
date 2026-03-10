from openai import OpenAI
from src.config import OPENAI_API_KEY, OPENAI_MODEL


class GPTClient:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL

    def review(self, prompt: str, document: str, max_tokens: int = 4000) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": document}
            ],
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content.strip()