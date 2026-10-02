from openai import OpenAI
from app.core.config import settings

def generate_answer(instructions, message):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        instructions=instructions,
        input=message,
    )

    answer = response.output_text.strip()
    return answer or "تعذر إنشاء إجابة حاليًا."
