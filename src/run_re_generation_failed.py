import os
import ia_generator
from dotenv import load_dotenv
import asyncio
import completion_data
import generator
import sqlite
import loaders

async def main():
    load_dotenv()

    organization = "org-eEal6XpWLgcgq2NOL2k6t7tn"
    api_key = os.getenv("OPENAI_API_KEY")

    category_dict = loaders.load_category_dict()
    completions_config = loaders.load_completions_config()

    connection = sqlite.get_sqlite_connection()
    sqlite.run_migrations(connection)
    
    completion_db = completion_data.CompletionDataDB(connection)
    openai_service = ia_generator.OpenAICompletionService(organization, api_key)
    article_generator = generator.ArticleGenerator(
        openai_service,
        completion_db,
        category_dict,
        completions_config
    )

    await article_generator.regenerate_articles()


asyncio.run(main())
