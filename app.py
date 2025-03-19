from flask import Flask, request, jsonify
from flask_cors import CORS

from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
import uuid
import chromadb

app = Flask(__name__)
CORS(app)  # Enable CORS

llm = ChatGroq(
    temperature=0, 
    groq_api_key='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', 
    model_name="llama-3.3-70b-versatile"
)

prompt_extract = PromptTemplate.from_template(
        """
        ### PERSON DESCRIPTION OF GOAL:
        {page_data}
        ### INSTRUCTION:
        The message is related to a person describing their goals for the future or their sources of pain.
        Your job is to summarise the goals mentioned or infer goals from the pain points by making the goal the opposite of the pain point seperated by commas.
        ### NO PREAMBLE
        """
)

client = chromadb.PersistentClient('vectorstore')
collection = client.get_or_create_collection(name="habitfinder")

@app.route('/')
def home():
    #data = request.get_json()

    goalmessage = "Im really ugly and I want to be more extroverted"

    chain_extract = prompt_extract | llm 
    res = chain_extract.invoke(input={'page_data':goalmessage})

    print(res.content) #this holds the output of the request

    goalsummary_raw = res.content.split(',')
    goalsummary = [item.strip() for item in goalsummary_raw]
    print(goalsummary)
            
    habitsummary = collection.query(query_texts=goalsummary, n_results=1).get('metadatas', [])
    print(str(habitsummary))

    response = {
        'habits':str(habitsummary)
    }

    print(response)

    return jsonify(response), 200


