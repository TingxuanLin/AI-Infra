from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"} 

@app.get("/generate")
def generate(prompt: str):
    return {
        "prompt": prompt,
        "status": "generated"
    }