import os
import openai
import csv
from dotenv import load_dotenv
from tqdm import tqdm
import markdown

CSV_HEADERS = ["keyword", "category", "metatitle", "metadesc", "raw_content", "html_content"]

def main():
    load_dotenv()

    openai.organization = "org-eEal6XpWLgcgq2NOL2k6t7tn"
    openai.api_key = os.getenv("OPENAI_API_KEY")

    keywords = load_keywords()

    start_generation(keywords)


def load_keywords() -> list[tuple[str, str]]:
    keywords: list[tuple[str, str]] = []
    with open("keywords.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        _ = next(reader)
        for row in reader:
            keywords.append((row[0], row[1]))

    return keywords


def start_generation(keywords: list[tuple[str, str]]):
    generated: list[tuple[str, str, str, str, str]] = []
    for title, category in tqdm(keywords):
        generated.append(generate_article(title, category))

    with open("generated.csv", "w", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(CSV_HEADERS)
        for row in generated:
            writer.writerow(row)


def generate_article(title: str, category: str):
    metatitle = generate_meta_title(title)
    metadesc = generate_meta_desc(title)
    markdown_content = generate_article_content(title)
    html_content = article_content_to_html(markdown_content)

    file_title = "".join([e for e in title.replace(" ", "_") if e.isalnum()])
    with open(f"{file_title}_generated.csv", "w", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow(CSV_HEADERS)
        writer.writerow([title, category, metatitle, metadesc, markdown_content, html_content])

    return (title, category, metatitle, metadesc, markdown_content, html_content)

def article_content_to_html(content: str) -> str:
    return markdown.markdown(content)

def generate_meta_desc(keyword: str) -> str:
    initial_prompt = f"""Genera un parrafo de metadescripción SEO para el keyword "{keyword}"."""

    return generate_completion(initial_prompt)


def generate_article_content(keyword: str) -> str:
    initial_prompt = f"""Escribe un web blog en formato markdown sobre "{keyword}". Con introducción y conclusiones. Escribe encabezados. Con palabras clave en negrita.  Explicalo con un tono cercano y casual. Que se pueda leer en 5 minutos. Añade emojis."""

    return generate_completion(initial_prompt)


def generate_meta_title(keyword: str) -> str:
    initial_prompt = f"""Genera un meta-título SEO para la keyword "{keyword}."""

    return generate_completion(initial_prompt)


def generate_completion(prompt: str, max_tokens=1024, temperature=0.2):
    _prompt = f"""{prompt}. Finaliza con la cadena <end>
    
    texto:
    """

    for _ in range(5):
        try:
            answer = openai.Completion.create(
                model="text-davinci-003",
                prompt=_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            generated_text: str = answer["choices"][0]["text"]
            prompt = prompt + generated_text

            if "<end>" in generated_text or generated_text == "":
                return generated_text.replace("<end>", "").strip()
        except Exception as e:
            print("Error ocurred: ", e)
            continue


main()
