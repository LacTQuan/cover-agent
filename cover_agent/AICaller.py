import datetime
import os
import time

import litellm
from functools import wraps
from wandb.sdk.data_types.trace_tree import Trace
from tenacity import retry, retry_if_exception_type, retry_if_not_exception_type, stop_after_attempt, wait_fixed
MODEL_RETRIES = 3


def conditional_retry(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.enable_retry:
            return func(self, *args, **kwargs)

        @retry(
            stop=stop_after_attempt(MODEL_RETRIES),
            wait=wait_fixed(1)
        )
        def retry_wrapper():
            return func(self, *args, **kwargs)

        return retry_wrapper()

    return wrapper

class AICaller:
    def __init__(self, model: str, prompt_path: str, api_base: str = "", enable_retry=True):
        """
        Initializes an instance of the AICaller class.

        Parameters:
            model (str): The name of the model to be used.
            api_base (str): The base API URL to use in case the model is set to Ollama or Hugging Face.
        """
        self.model = model
        self.api_base = api_base
        self.enable_retry = enable_retry
        self.prompt_path = prompt_path

    @conditional_retry  # You can access self.enable_retry here
    def call_model(self, prompt: dict, max_tokens=4096, stream=True):
        """
        Call the language model with the provided prompt and retrieve the response.

        Parameters:
            prompt (dict): The prompt to be sent to the language model.
            max_tokens (int, optional): The maximum number of tokens to generate in the response. Defaults to 4096.
            stream (bool, optional): Whether to stream the response or not. Defaults to True.

        Returns:
            tuple: A tuple containing the response generated by the language model, the number of tokens used from the prompt, and the total number of tokens in the response.
        """
        if "system" not in prompt or "user" not in prompt:
            raise KeyError(
                "The prompt dictionary must contain 'system' and 'user' keys."
            )
        
        # Append the prompt to the prompt_path
        if self.prompt_path:
            with open(self.prompt_path, "a") as f:
                f.write(f"system: {prompt['system']}\n")
                f.write(f"user: {prompt['user']}\n\n")

        if prompt["system"] == "":
            messages = [{"role": "user", "content": prompt["user"]}]
        else:
            if self.model in ["o1-preview", "o1-mini"]:
                # o1 doesn't accept a system message so we add it to the prompt
                messages = [
                    {"role": "user", "content": prompt["system"] + "\n" + prompt["user"]},
                ]
            else:
                messages = [
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": prompt["user"]},
                ]

        # Default completion parameters
        completion_params = {
            "model": self.model,
            "messages": messages,
            "stream": stream,  # Use the stream parameter passed to the method
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }

        # Model-specific adjustments
        if self.model in ["o1-preview", "o1-mini"]:
            stream = False  # o1 doesn't support streaming
            completion_params["temperature"] = 1
            completion_params["stream"] = False  # o1 doesn't support streaming
            completion_params["max_completion_tokens"] = max_tokens
            completion_params.pop("max_tokens", None)  # Remove 'max_tokens' if present

        # API base exception for OpenAI Compatible, Ollama, and Hugging Face models
        if (
            "ollama" in self.model
            or "huggingface" in self.model
            or self.model.startswith("openai/")
        ):
            completion_params["api_base"] = self.api_base

        try:
            response = litellm.completion(**completion_params)
        except Exception as e:
            print(f"Error calling LLM model: {e}")
            raise e

        if stream:
            chunks = []
            print("Streaming results from LLM model...")
            try:
                for chunk in response:
                    print(chunk.choices[0].delta.content or "", end="", flush=True)
                    chunks.append(chunk)
                    time.sleep(
                        0.01
                    )  # Optional: Delay to simulate more 'natural' response pacing

            except Exception as e:
                print(f"Error calling LLM model during streaming: {e}")
                if self.enable_retry:
                    raise e
            model_response = litellm.stream_chunk_builder(chunks, messages=messages)
            print("\n")
            # Build the final response from the streamed chunks
            content = model_response["choices"][0]["message"]["content"]
            usage = model_response["usage"]
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])

            result_path = self.prompt_path.replace("prompt", "result")
            with open(result_path, "a") as f:
                f.write(content + "\n")
        else:
            # Non-streaming response is a CompletionResponse object
            content = response.choices[0].message.content
            print(f"Printing results from LLM model...\n{content}")
            usage = response.usage
            prompt_tokens = int(usage.prompt_tokens)
            completion_tokens = int(usage.completion_tokens)

        if "WANDB_API_KEY" in os.environ:
            try:
                root_span = Trace(
                    name="inference_"
                    + datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                    kind="llm",  # kind can be "llm", "chain", "agent", or "tool"
                    inputs={
                        "user_prompt": prompt["user"],
                        "system_prompt": prompt["system"],
                    },
                    outputs={"model_response": content},
                )
                root_span.log(name="inference")
            except Exception as e:
                print(f"Error logging to W&B: {e}")

        # Returns: Response, Prompt token count, and Completion token count

        # Just want to ensure that content is in yaml format, remove the content which is wrapped with <div> tag

        return content, prompt_tokens, completion_tokens

