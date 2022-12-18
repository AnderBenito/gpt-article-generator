import os
import openai
import csv
from dotenv import load_dotenv
from tqdm import tqdm
import markdown
from concurrent import futures
import asyncio


CSV_HEADERS = ["keyword", "category", "metatitle",
               "metadesc", "raw_content", "html_content"]

GENERATED_DIR_PATH = "generated"
GENERATED_FILE_NAME = "generated.csv"
ARTIFACTS_DIR_PATH = "generated/keywords"

sem = asyncio.Semaphore(10)


async def main():
    load_dotenv()

    openai.organization = "org-eEal6XpWLgcgq2NOL2k6t7tn"
    openai.api_key = os.getenv("OPENAI_API_KEY")

    keywords = load_keywords()

    await start_generation(keywords)


def load_keywords() -> list[tuple[str, str]]:
    keywords: list[tuple[str, str]] = []
    with open("keywords.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        _ = next(reader)
        for row in reader:
            keywords.append((row[0], row[1]))

    return keywords


async def start_generation(keywords: list[tuple[str, str]]):
    generated: list[tuple[str, str, str, str, str]] = []

    generated = await asyncio.gather(
        *[safe_generate_article_async(title, category) for title, category in keywords]
    )

    if not os.path.exists(GENERATED_DIR_PATH):
        os.makedirs(GENERATED_DIR_PATH)
    with open(f"{GENERATED_DIR_PATH}/{GENERATED_FILE_NAME}", "w", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(CSV_HEADERS)
        for row in generated:
            writer.writerow(row)


async def safe_generate_article_async(title: str, category: str):
    async with sem:
        return await generate_article(title, category)


async def generate_article(title: str, category: str):


    metatitle, metadesc, markdown_content = await asyncio.gather(
        generate_meta_title(title),
        generate_meta_desc(title),
        generate_article_content(title),
    )

    html_content = article_content_to_html(markdown_content)

    file_title = "".join([e for e in title.replace(" ", "_") if e.isalnum()])

    if not os.path.exists(ARTIFACTS_DIR_PATH):
        os.makedirs(ARTIFACTS_DIR_PATH)
    with open(f"{ARTIFACTS_DIR_PATH}/{file_title}_generated.csv", "w", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(CSV_HEADERS)
        writer.writerow([title, category, metatitle, metadesc,
                        markdown_content, html_content])

    print(f"{title} article contents generated")
    return (title, category, metatitle, metadesc, markdown_content, html_content)


def article_content_to_html(content: str) -> str:
    return markdown.markdown(content)


async def generate_meta_desc(keyword: str) -> str:
    initial_prompt = f"""Genera un parrafo de metadescripción SEO de menos de 155 caracteres sobre "{keyword}"."""

    return await generate_completion(initial_prompt, max_tokens=170)


async def generate_article_content(keyword: str) -> str:
    initial_prompt = f"""Escribe artículo estilo medium en formato markdown sobre {keyword}. Con introducción, y encabezados. Explicalo de forma detallada pero con un tono cercano. Añade emojis y palabras en negrita."""

    return await generate_completion(initial_prompt, temperature=0.5, presence_penalty=0.5)


async def generate_meta_title(keyword: str) -> str:
    initial_prompt = f"""Genera un meta-título SEO para la keyword "{keyword}" con menos de 57 caracteres y sin separadores."""

    return await generate_completion(initial_prompt, max_tokens=45)


async def generate_completion(prompt: str, max_tokens=1024, temperature=0.2, presence_penalty=0):
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


asyncio.run(main())
