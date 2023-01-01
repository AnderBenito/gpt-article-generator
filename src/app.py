import os
from typing import Callable
import requests
from dataclasses import dataclass
import openai
import csv
from dotenv import load_dotenv
from tqdm import tqdm
import markdown
from concurrent import futures
import asyncio

@dataclass
class CompletionInput:
    keyword: str
    category: str

@dataclass
class GeneratedCompletionData:
    keyword: str
    category: str
    title: str
    content: str
    html_content: str
    meta_title: str
    meta_desc: str
    img_url: str

@dataclass
class CompletionsConfig:
    generate_images: bool
    title_pipe: Callable[[CompletionInput], str]
    content_prompt_pipe: Callable[[CompletionInput], str]
    meta_title_prompt_pipe: Callable[[CompletionInput], str]
    meta_desc_prompt_pipe: Callable[[CompletionInput], str]



CSV_HEADERS = [
    "keyword", 
    "title", 
    "category", 
    "metatitle",
    "metadesc", 
    "raw_content", 
    "html_content", 
    "img_url",
    ]

GENERATED_DIR_PATH = "generated"
GENERATED_FILE_NAME = "generated.csv"
ARTIFACTS_DIR_PATH = "generated/keywords"

sem = asyncio.Semaphore(4)

async def main():
    load_dotenv()

    completions_config = CompletionsConfig(
        generate_images=True,
        title_pipe=lambda input: f"""Titulo - {input.keyword}""",
        content_prompt_pipe=lambda input: f"""Escribe artículo estilo medium en formato markdown sobre {input.keyword}. Con introducción, y encabezados. Explicalo de forma detallada pero con un tono cercano. Añade emojis y palabras en negrita.""",
        meta_desc_prompt_pipe=lambda input: f"""Genera un parrafo de metadescripción SEO de menos de 155 caracteres sobre "{input.keyword}".""",
        meta_title_prompt_pipe=lambda input: f"""Genera un meta-título SEO para la keyword "{input.keyword}" con menos de 57 caracteres y sin separadores."""
    )

    openai.organization = "org-eEal6XpWLgcgq2NOL2k6t7tn"
    openai.api_key = os.getenv("OPENAI_API_KEY")

    keywords = load_keywords()

    await start_generation(keywords, completions_config)


def load_keywords() -> list[CompletionInput]:
    keywords: list[tuple[str, str]] = []
    with open("keywords.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        _ = next(reader)
        for row in reader:
            keywords.append(CompletionInput(row[0], row[1]))

    return keywords


async def start_generation(inputs: list[CompletionInput], config: CompletionsConfig):
    generated: list[GeneratedCompletionData] = []

    generated = await asyncio.gather(
        *[safe_generate_article_async(input, config) for input in inputs]
    )

    if not os.path.exists(GENERATED_DIR_PATH):
        os.makedirs(GENERATED_DIR_PATH)
    with open(f"{GENERATED_DIR_PATH}/{GENERATED_FILE_NAME}", "w", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(CSV_HEADERS)
        for row in generated:
            writer.writerow([
            row.keyword, 
            row.title, 
            row.category, 
            row.meta_title,
            row.meta_desc, 
            row.content, 
            row.html_content, 
            row.img_url,
            ])


async def safe_generate_article_async(input: CompletionInput, config: CompletionsConfig):
    async with sem:
        return await generate_article(input, config)


async def generate_article(input: CompletionInput, config: CompletionsConfig):
    title = config.title_pipe(input)

    metatitle, metadesc, raw_content, img_url = await asyncio.gather(
        generate_meta_title(input, config),
        generate_meta_desc(input, config),
        generate_article_content(input, config),
        get_img_url(input, config),
    )

    html_content = article_content_to_html(raw_content)

    file_title = "".join([e for e in title.replace(" ", "_") if e.isalnum()])

    if not os.path.exists(ARTIFACTS_DIR_PATH):
        os.makedirs(ARTIFACTS_DIR_PATH)
    with open(f"{ARTIFACTS_DIR_PATH}/{file_title}_generated.csv", "w", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(CSV_HEADERS)
        writer.writerow([title, title, input.category, metatitle, metadesc,
                        html_content, html_content, img_url])

    print(f"{title} article contents generated")
    return GeneratedCompletionData(
        keyword=input.keyword,
        category=input.category,
        content=raw_content,
        html_content=html_content,
        meta_desc=metadesc,
        meta_title=metatitle,
        title=title,
        img_url=img_url
    )


def article_content_to_html(content: str) -> str:
    return markdown.markdown(content)


async def generate_meta_desc(input: CompletionInput, config: CompletionsConfig) -> str:
    initial_prompt = config.meta_desc_prompt_pipe(input)

    return await generate_completion(initial_prompt, max_tokens=130)


async def generate_article_content(input: CompletionInput, config: CompletionsConfig) -> str:
    initial_prompt = config.content_prompt_pipe(input)

    return await generate_completion(initial_prompt, max_tokens=3711, temperature=0.5, presence_penalty=0.5)


async def generate_meta_title(input: CompletionInput, config: CompletionsConfig) -> str:
    initial_prompt = config.meta_title_prompt_pipe(input)

    return await generate_completion(initial_prompt, max_tokens=45)


async def generate_completion(prompt: str, max_tokens=1024, temperature=0.2, presence_penalty=0):
    return ""
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

async def get_img_url(input: CompletionInput, config: CompletionsConfig):
    url = "https://bing-image-search1.p.rapidapi.com/images/search"

    querystring = {"q":f"{input.keyword}","count":"1","mkt":"es-ES"}

    headers = {
        "X-RapidAPI-Key": "e9b91ef8b6msha9f0861e95a5b3dp11fcfajsn191712ccf51f",
        "X-RapidAPI-Host": "bing-image-search1.p.rapidapi.com"
    }

    loop = asyncio.get_event_loop() 
    response = await loop.run_in_executor(
        None,
        lambda: requests.request("GET", url, headers=headers, params=querystring)
    )

    if response.status_code != 200:
        return ""

    values = response.json()["value"]

    if values is None or len(values) == 0:
        return ""
    
    return values[0]["contentUrl"]

asyncio.run(main())
