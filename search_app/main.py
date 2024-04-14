import os

import requests
import uvicorn
from fastapi import FastAPI
from langchain.chat_models.gigachat import GigaChat
from langchain.schema import HumanMessage, SystemMessage
from pydantic import BaseModel
from pymilvus import MilvusClient

auth_gigachat = os.getenv('GIGACHAT')
EMBEDDER_ADDRESS = f"http://{os.getenv('EMBEDDER_ADDRESS')}"
MILVUS_ADDRESS = f"http://{os.getenv('MILVUS_ADDRESS')}"

client = MilvusClient(uri=MILVUS_ADDRESS)
COLLECTION_NAME = "LaBSE_embeddings_3"
client.load_collection(COLLECTION_NAME)

llm = GigaChat(credentials=auth_gigachat, verify_ssl_certs=False)
system_message = SystemMessage(
    content="Ты профессионально и объёмно отвечаешь на вопросы, используя свои собственные знания и контекст в сообщениях"
)

app = FastAPI()


class Query(BaseModel):
    query: str


class Response(BaseModel):
    answer: str
    document_ids: list[str]


@app.post("/search/", response_model=Response)
def search(query: Query, use_hyde: str = 'false'):
    query_for_embedder = query.query
    if use_hyde == 'true':
        print("Using HyDE technique")
        hypotetic_document = llm.invoke([
            system_message,
            HumanMessage(content=query.query)
        ])
        if hypotetic_document.response_metadata["finish_reason"] != 'blacklist':
            query_for_embedder = hypotetic_document.content
            print(f"Query for embedder: {query_for_embedder}")
    embedding = requests.post(EMBEDDER_ADDRESS, json={"query": query_for_embedder}).json()
    search_result = client.search(COLLECTION_NAME, [embedding], limit=15, output_fields=['text'])
    context = "\n".join(
        [s["entity"]["text"] for s in search_result[0]]
    )
    doc_ids = [str(s["id"]) for s in search_result[0]]
    messages = [
        system_message,
        HumanMessage(
            content=f"{context}\n\n Опираясь на предоставленную информацию ответь на вопрос:\n {query}"
        )
    ]
    answer = llm.invoke(messages)
    return {"answer": answer.content, "document_ids": doc_ids}


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv('PORT')))
