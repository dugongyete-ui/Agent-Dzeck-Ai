import time
import datetime
import uuid
import os
import sys
import json
from typing import List, Tuple, Type, Dict, Optional
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import configparser

from sources.utility import timer_decorator, pretty_print, animate_thinking
from sources.logger import Logger

config = configparser.ConfigParser()
config.read('config.ini')

class Memory():
    """
    Memory is a class for managing the conversation memory
    It provides a method to compress the memory using summarization model.
    """
    def __init__(self, system_prompt: str,
                 recover_last_session: bool = False,
                 memory_compression: bool = True,
                 model_provider: str = "deepseek-r1:14b"):
        self.memory = [{'role': 'system', 'content': system_prompt}]
        
        self.logger = Logger("memory.log")
        self.session_time = datetime.datetime.now()
        self.session_id = str(uuid.uuid4())
        self.conversation_folder = f"conversations/"
        self.session_recovered = False
        if recover_last_session:
            self.load_memory()
            self.session_recovered = True
        self.model = None
        self.tokenizer = None
        self.device = self.get_cuda_device()
        self.memory_compression = memory_compression
        self.model_provider = model_provider
        if self.memory_compression:
            self.download_model()

    def get_ideal_ctx(self, model_name: str) -> Optional[int]:
        import re
        import math

        def extract_number_before_b(sentence: str) -> int:
            match = re.search(r'(\d+)b', sentence, re.IGNORECASE)
            return int(match.group(1)) if match else None

        model_size = extract_number_before_b(model_name)
        if not model_size:
            return None
        base_size = 7
        base_context = 4096
        scaling_factor = 1.5
        context_size = int(base_context * (model_size / base_size) ** scaling_factor)
        context_size = 2 ** round(math.log2(context_size))
        self.logger.info(f"Estimated context size for {model_name}: {context_size} tokens.")
        return context_size
    
    def download_model(self):
        """Download the model if not already downloaded."""
        animate_thinking("Loading memory compression model...", color="status")
        self.tokenizer = AutoTokenizer.from_pretrained("pszemraj/led-base-book-summary")
        self.model = AutoModelForSeq2SeqLM.from_pretrained("pszemraj/led-base-book-summary")
        self.logger.info("Memory compression system initialized.")
    
    def get_filename(self) -> str:
        return f"memory_{self.session_time.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    
    def save_memory(self, agent_type: str = "casual_agent") -> None:
        if not os.path.exists(self.conversation_folder):
            self.logger.info(f"Created folder {self.conversation_folder}.")
            os.makedirs(self.conversation_folder)
        save_path = os.path.join(self.conversation_folder, agent_type)
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        filename = self.get_filename()
        path = os.path.join(save_path, filename)
        json_memory = json.dumps(self.memory)
        with open(path, 'w') as f:
            self.logger.info(f"Saved memory json at {path}")
            f.write(json_memory)
    
    def find_last_session_path(self, path) -> Optional[str]:
        saved_sessions = []
        for filename in os.listdir(path):
            if filename.startswith('memory_'):
                date = filename.split('_')[1]
                saved_sessions.append((filename, date))
        saved_sessions.sort(key=lambda x: x[1], reverse=True)
        if len(saved_sessions) > 0:
            self.logger.info(f"Last session found at {saved_sessions[0][0]}")
            return saved_sessions[0][0]
        return None
    
    def save_json_file(self, path: str, json_memory: dict) -> None:
        try:
            with open(path, 'w') as f:
                json.dump(json_memory, f)
                self.logger.info(f"Saved memory json at {path}")
        except Exception as e:
            self.logger.warning(f"Error saving file {path}: {e}")
    
    def load_json_file(self, path: str) -> dict:
        json_memory = {}
        try:
            with open(path, 'r') as f:
                json_memory = json.load(f)
        except FileNotFoundError:
            self.logger.warning(f"File not found: {path}")
            return {}
        except json.JSONDecodeError:
            self.logger.warning(f"Error decoding JSON from file: {path}")
            return {}
        except Exception as e:
            self.logger.warning(f"Error loading file {path}: {e}")
            return {}
        return json_memory

    def load_memory(self, agent_type: str = "casual_agent") -> None:
        if self.session_recovered == True:
            return
        pretty_print(f"Loading {agent_type} past memories... ", color="status")
        save_path = os.path.join(self.conversation_folder, agent_type)
        if not os.path.exists(save_path):
            pretty_print("No memory to load.", color="success")
            return
        filename = self.find_last_session_path(save_path)
        if filename is None:
            pretty_print("Last session memory not found.", color="warning")
            return
        path = os.path.join(save_path, filename)
        self.memory = self.load_json_file(path) 
        if isinstance(self.memory, list) and len(self.memory) > 0 and self.memory[-1]['role'] == 'user':
            self.memory.pop()
        self.compress()
        pretty_print("Session recovered successfully", color="success")
    
    def reset(self, memory: list = None) -> None:
        self.logger.info("Memory reset performed.")
        if memory is not None:
            self.memory = memory
        elif len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            self.memory = [self.memory[0]]
        else:
            self.memory = []
    
    def push(self, role: str, content: str) -> int:
        ideal_ctx = self.get_ideal_ctx(self.model_provider)
        if ideal_ctx is not None:
            if self.memory_compression and len(content) > ideal_ctx * 1.5:
                self.logger.info(f"Compressing memory: Content {len(content)} > {ideal_ctx} model context.")
                self.compress()
        curr_idx = len(self.memory)
        if curr_idx > 0 and self.memory[curr_idx-1]['content'] == content:
            pretty_print("Warning: same message have been pushed twice to memory", color="error")
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if config["MAIN"]["provider_name"] == "openrouter":
            self.memory.append({'role': role, 'content': content})
        else:
            self.memory.append({'role': role, 'content': content, 'time': time_str, 'model_used': self.model_provider})
        return curr_idx-1
    
    def clear(self) -> None:
        self.logger.info("Memory clear performed.")
        self.memory = self.memory[:1]
    
    def clear_section(self, start: int, end: int) -> None:
        self.logger.info(f"Clearing memory section {start} to {end}.")
        start = max(0, start) + 1
        end = min(end, len(self.memory)-1) + 2
        self.memory = self.memory[:start] + self.memory[end:]
    
    def get(self) -> list:
        return [{'role': msg['role'], 'content': msg['content']} for msg in self.memory]

    def get_cuda_device(self) -> str:
        if torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda"
        else:
            return "cpu"

    def summarize(self, text: str, min_length: int = 64) -> str:
        if self.tokenizer is None or self.model is None:
            self.logger.warning("No tokenizer or model to perform summarization.")
            return text
        if len(text) < min_length*1.5:
            return text
        max_length = len(text) // 2 if len(text) > min_length*2 else min_length*2
        input_text = "summarize: " + text
        inputs = self.tokenizer(input_text, return_tensors="pt", max_length=512, truncation=True)
        summary_ids = self.model.generate(
            inputs['input_ids'],
            max_length=max_length,
            min_length=min_length,
            length_penalty=1.0,
            num_beams=4,
            early_stopping=True
        )
        summary = self.tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        summary = summary.replace('summary:', '')
        self.logger.info(f"Memory summarized from len {len(text)} to {len(summary)}.")
        self.logger.info(f"Summarized text:\n{summary}")
        return summary
    
    def compress(self) -> Optional[str]:
        if self.tokenizer is None or self.model is None:
            self.logger.warning("No tokenizer or model to perform memory compression.")
            return
        for i in range(len(self.memory)):
            if self.memory[i]['role'] == 'system':
                continue
            if len(self.memory[i]['content']) > 1024:
                self.memory[i]['content'] = self.summarize(self.memory[i]['content'])
    
    def trim_text_to_max_ctx(self, text: str) -> str:
        ideal_ctx = self.get_ideal_ctx(self.model_provider)
        return text[:ideal_ctx] if ideal_ctx is not None else text
    
    def compress_text_to_max_ctx(self, text) -> str:
        if self.tokenizer is None or self.model is None:
            self.logger.warning("No tokenizer or model to perform memory compression.")
            return text
        ideal_ctx = self.get_ideal_ctx(self.model_provider)
        if ideal_ctx is None:
            self.logger.warning("No ideal context size found.")
            return text
        while len(text) > ideal_ctx:
            self.logger.info(f"Compressing text: {len(text)} > {ideal_ctx} model context.")
            text = self.summarize(text)
        return text


if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    memory = Memory("You are a helpful assistant.",
                    recover_last_session=False, memory_compression=True)

    memory.push('user', "hello")
    memory.push('assistant', "how can i help you?")
    memory.push('user', "why do i get this cuda error?")
    sample_text = """
The error you're encountering:
cuda.cu:52:10: fatal error: helper_functions.h: No such file or directory
 #include <helper_functions.h>
indicates that the compiler cannot find the helper_functions.h file.
    """
    memory.push('assistant', sample_text)
    
    print("\n---\nmemory before:", memory.get())
    memory.compress()
    print("\n---\nmemory after:", memory.get())
