import os
import requests
import time
from dotenv import load_dotenv
from openai import OpenAI

from sources.logger import Logger
from sources.utility import pretty_print, animate_thinking

HUGGINGFACE_FREE_MODELS = [
    "Qwen/Qwen2.5-72B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mixtral-8x7B-Instruct-v0.1",
]


class Provider:
    def __init__(self, provider_name, model, server_address="127.0.0.1:5000", is_local=False):
        self.provider_name = provider_name.lower()
        self.model = model
        self.is_local = is_local
        self.server_ip = server_address
        self.server_address = server_address
        self.available_providers = {
            "groq": self.groq_fn,
            "huggingface": self.huggingface_fn,
            "test": self.test_fn
        }
        self.logger = Logger("provider.log")
        self.api_key = None
        self.unsafe_providers = ["groq", "huggingface"]
        if self.provider_name not in self.available_providers:
            raise ValueError(f"Provider tidak dikenal: {provider_name}. Provider yang tersedia: groq, huggingface")
        if self.provider_name in self.unsafe_providers and self.is_local == False:
            pretty_print(f"Menggunakan provider API: {provider_name}. Data akan dikirim ke cloud.", color="warning")
            self.api_key = self.get_api_key(self.provider_name)

    def get_model_name(self) -> str:
        return self.model

    def get_api_key(self, provider):
        load_dotenv()
        api_key_var = f"{provider.upper()}_API_KEY"
        api_key = os.getenv(api_key_var)
        if not api_key:
            pretty_print(f"API key {api_key_var} tidak ditemukan. Silakan set sebagai environment variable/secret.", color="warning")
            raise ValueError(f"API key {api_key_var} tidak ditemukan. Set sebagai environment variable.")
        return api_key

    def respond(self, history, verbose=True):
        llm = self.available_providers[self.provider_name]
        self.logger.info(f"Using provider: {self.provider_name}")
        max_retries = 2
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                thought = llm(history, verbose)
                return thought
            except KeyboardInterrupt:
                self.logger.warning("User interrupted the operation with Ctrl+C")
                return "Operation interrupted by user. REQUEST_EXIT"
            except ConnectionError as e:
                raise ConnectionError(f"{str(e)}\nKoneksi ke {self.server_ip} gagal.")
            except AttributeError as e:
                raise NotImplementedError(f"{str(e)}\nApakah {self.provider_name} sudah diimplementasi?")
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError(
                    f"{str(e)}\nImport terkait provider {self.provider_name} tidak ditemukan. Sudah terinstall?")
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if "402" in error_str or "payment required" in error_str or "credit" in error_str or "depleted" in error_str:
                    self.logger.warning(f"Kredit habis untuk {self.provider_name}/{self.model}, mencoba model lain...")
                    if self.provider_name == "huggingface":
                        fallback = self._try_huggingface_fallback(history, verbose)
                        if fallback is not None:
                            return fallback
                    return "Kredit API habis. Silakan periksa akun HuggingFace Anda atau ganti ke provider Groq melalui pengaturan Model AI di sidebar."
                if "rate_limit" in error_str or "429" in error_str or "rate limit" in error_str:
                    if attempt < max_retries:
                        wait_time = (attempt + 1) * 3
                        self.logger.info(f"Rate limited, menunggu {wait_time}s sebelum retry...")
                        time.sleep(wait_time)
                        continue
                    return "Batas penggunaan API tercapai. Silakan tunggu beberapa menit dan coba lagi."
                if "try again later" in error_str or "503" in error_str or "overloaded" in error_str:
                    if attempt < max_retries:
                        time.sleep(2)
                        continue
                    return f"{self.provider_name} server sedang sibuk. Coba lagi nanti."
                if "refused" in error_str:
                    return f"Server {self.server_ip} tampak offline. Tidak bisa menjawab."
                if attempt < max_retries:
                    self.logger.info(f"Retry attempt {attempt + 1} after error: {str(e)}")
                    time.sleep(1)
                    continue
                raise Exception(f"Provider {self.provider_name} gagal: {str(e)}") from e
        if last_error:
            raise Exception(f"Provider {self.provider_name} gagal setelah {max_retries + 1} percobaan: {str(last_error)}") from last_error

    def _try_huggingface_fallback(self, history, verbose):
        from huggingface_hub import InferenceClient
        api_key = self.get_api_key("huggingface")
        fallback_models = [m for m in HUGGINGFACE_FREE_MODELS if m != self.model]
        for model in fallback_models:
            try:
                self.logger.info(f"Mencoba fallback model: {model}")
                client = InferenceClient(api_key=api_key)
                completion = client.chat.completions.create(
                    model=model,
                    messages=history,
                    max_tokens=4096,
                )
                thought = completion.choices[0].message
                self.logger.info(f"Fallback model {model} berhasil!")
                self.model = model
                return thought.content
            except Exception as e:
                self.logger.warning(f"Fallback model {model} gagal: {str(e)}")
                continue
        return None

    def groq_fn(self, history, verbose=False):
        client = OpenAI(api_key=self.api_key, base_url="https://api.groq.com/openai/v1")
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=history,
            )
            if response is None:
                raise Exception("Groq response kosong.")
            thought = response.choices[0].message.content
            if verbose:
                print(thought)
            return thought
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}") from e

    def huggingface_fn(self, history, verbose=False):
        from huggingface_hub import InferenceClient
        client = InferenceClient(
            api_key=self.get_api_key("huggingface")
        )
        completion = client.chat.completions.create(
            model=self.model,
            messages=history,
            max_tokens=4096,
        )
        thought = completion.choices[0].message
        return thought.content

    def test_fn(self, history, verbose=True):
        thought = """
\n\n```json\n{\n  "plan": [\n    {\n      "agent": "Web",\n      "id": "1",\n      "need": null,\n      "task": "Conduct a comprehensive web search to identify at least five AI startups located in Osaka."\n    },\n    {\n      "agent": "File",\n      "id": "2",\n      "need": ["1"],\n      "task": "Create a new text file named research_japan.txt."\n    }\n  ]\n}\n```
        """
        return thought


if __name__ == "__main__":
    provider = Provider("groq", "llama-3.3-70b-versatile")
    res = provider.respond([{"role": "user", "content": "Hello, how are you?"}])
    print("Response:", res)
