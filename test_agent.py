from app.tools.rag_tool import get_rag_retriever
from app.graph import run_agent # Import the wrapper function

def test_rag():
    print("Initializing retriever...")
    retriever = get_rag_retriever()
    print("Querying vector store...")
    results = retriever.invoke("What are the tax deadlines?")
    if not results:
        print("No documents found!")
    else:
        for doc in results:
            print(f"\n--- Found Document ---")
            print(f"Content: {doc.page_content[:100]}...")

def test_agent():
    print("\n--- Testing Railguard ---")
    response = run_agent("What is the capital of France?")
    print(f"Agent Response: {response['messages'][-1].content}")

    print("\n--- Testing RAG Retrieval ---")
    response = run_agent("What are the tax deadlines mentioned in the document?")
    print(f"Agent Response: {response['messages'][-1].content}")

if __name__ == "__main__":
    test_rag()
    test_agent()