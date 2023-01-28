import openai
import asyncio

class OpenAICompletionService:
  api_key: str
  organization: str

  def __init__(self, organization: str, api_key: str) -> None:
    self.organization = organization
    self.api_key = api_key
    openai.organization = organization
    openai.api_key = api_key
    
  async def generate_completion(self, prompt: str, max_tokens=1024, temperature=0.2, presence_penalty=0):
    _prompt = f"""{prompt}. Finaliza con la cadena <end>

    texto:
    """

    for _ in range(5):
        try:
            loop = asyncio.get_event_loop()
            answer = await loop.run_in_executor(None, lambda: openai.Completion.create(
                model="text-davinci-003",
                prompt=_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                presence_penalty=presence_penalty,
            ))

            generated_text: str = answer["choices"][0]["text"]
            prompt = prompt + generated_text

            if "<end>" in generated_text or generated_text == "":
                return generated_text.replace("<end>", "").strip()
        except Exception as e:
            print("Error ocurred in completion: ", e)
            continue
      