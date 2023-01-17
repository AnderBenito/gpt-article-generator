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
    raw_content: str
    cleaned_content: str
    html_content: str
    meta_title: str
    meta_desc: str
    img_url: str
    img_attribution_username: str

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
    "cleaned_content",
    "html_content",
    "img_url",
    "img_attribution_username"
    ]

GENERATED_DIR_PATH = "generated"
GENERATED_FILE_NAME = "generated.csv"
ARTIFACTS_DIR_PATH = "generated/keywords"

sem = asyncio.Semaphore(4)

async def main():
    load_dotenv()

    completions_config = CompletionsConfig(
        generate_images=True,
        title_pipe=lambda input: f"""{input.keyword}""",
        content_prompt_pipe=lambda input: f"""Somos una página web que escribe artículos sobre inclusión educativa. Escribimos los artículos con un tono cercano y profesional. Hacemos artículos con buen SEO y de calidad.
Escribe artículo estilo medium en formato html sobre {input.keyword}. Con introducción, y encabezados. Con palabras en <strong>.""",
        meta_desc_prompt_pipe=lambda input: f"""Genera un parrafo de metadescripción SEO de menos de 155 caracteres sobre "{input.keyword}".""",
        meta_title_prompt_pipe=lambda input: f"""Genera un meta-título SEO para la keyword "{input.keyword}" con menos de 57 caracteres y sin separadores."""
    )

    openai.organization = "org-eEal6XpWLgcgq2NOL2k6t7tn"
    openai.api_key = os.getenv("OPENAI_API_KEY")

    keywords = load_keywords()
    category_dict = load_category_dict()

    await start_generation(keywords, category_dict, completions_config)


def load_keywords() -> list[CompletionInput]:
    keywords: list[tuple[str, str]] = []
    with open("keywords.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        _ = next(reader)
        for row in reader:
            keywords.append(CompletionInput(row[0], row[1]))

    return keywords

def load_category_dict() -> dict[str, str]:
    category_dict = dict[str, str]()
    with open("categories.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        _ = next(reader)
        for row in reader:
            category_dict[row[0]] = row[1]

    return category_dict

async def start_generation(inputs: list[CompletionInput], category_dict: dict[str, str], config: CompletionsConfig):
    generated: list[GeneratedCompletionData] = []

    generated = await asyncio.gather(
        *[safe_generate_article_async(input, category_dict, config) for input in inputs]
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
            row.raw_content,
            row.cleaned_content, 
            row.html_content, 
            row.img_url,
            row.img_attribution_username
            ])


async def safe_generate_article_async(input: CompletionInput, category_dict: dict[str, str], config: CompletionsConfig):
    async with sem:
        return await generate_article(input, category_dict, config)


async def generate_article(input: CompletionInput, category_dict: dict[str, str], config: CompletionsConfig):
    title = config.title_pipe(input)

    metatitle, metadesc, raw_content, img_data = await asyncio.gather(
        generate_meta_title(input, config),
        generate_meta_desc(input, config),
        generate_article_content(input, config),
        get_img_url(input, category_dict, config),
    )

    replaced = raw_content.replace("\r\n", "\n").replace("\r", "")

    # Remove first line to remote title from content
    cleaned_content = "\n".join(replaced.split("\n")[1:])

    html_content = article_content_to_html(cleaned_content)

    file_title = "".join([e for e in title.replace(" ", "_") if e.isalnum()])

    if not os.path.exists(ARTIFACTS_DIR_PATH):
        os.makedirs(ARTIFACTS_DIR_PATH)
    with open(f"{ARTIFACTS_DIR_PATH}/{file_title}_generated.csv", "w", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(CSV_HEADERS)
        writer.writerow([
            title,
            title,
            input.category,
            metatitle,
            metadesc,
            raw_content,
            cleaned_content,
            html_content,
            img_data[0],
            img_data[1]
        ])

    print(f"{title} article contents generated")
    return GeneratedCompletionData(
        keyword=input.keyword,
        category=input.category,
        raw_content=raw_content,
        cleaned_content=cleaned_content,
        html_content=html_content,
        meta_desc=metadesc,
        meta_title=metatitle,
        title=title,
        img_url=img_data[0],
        img_attribution_username=img_data[1]
    )


def article_content_to_html(content: str) -> str:
    return markdown.markdown(content)


async def generate_meta_desc(input: CompletionInput, config: CompletionsConfig) -> str:
    initial_prompt = config.meta_desc_prompt_pipe(input)

    return await generate_completion(initial_prompt, max_tokens=130)


async def generate_article_content(input: CompletionInput, config: CompletionsConfig) -> str:
    initial_prompt = config.content_prompt_pipe(input)

    completion = await generate_completion(initial_prompt, max_tokens=3711, temperature=0.5, presence_penalty=0.5)

    return completion


async def generate_meta_title(input: CompletionInput, config: CompletionsConfig) -> str:
    initial_prompt = config.meta_title_prompt_pipe(input)

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

async def get_img_url(
    input: CompletionInput,
    category_dict: dict[str, str],
    config: CompletionsConfig
    ) -> tuple[str, str]:
    url = "https://api.unsplash.com/photos/random"

    img_query = category_dict[input.category]
    querystring = {"query":f"{img_query}","count":"1"}

    headers = {
        "Authorization": "Client-ID O-SVzn6X_ue1XqzoSCZdMdGiUd-XZ21bw8B_xWyU9Ic"
    }

    loop = asyncio.get_event_loop() 
    response = await loop.run_in_executor(
        None,
        lambda: requests.request("GET", url, headers=headers, params=querystring)
    )

    if response.status_code != 200:
        return ["", ""]

    values = response.json()

    if values is None or len(values) == 0:
        return ["", ""]
    

    return [values[0]["urls"]["full"], values[0]["user"]["username"]]

asyncio.run(main())
