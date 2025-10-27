import traceback
from os import PathLike
from aiofiles import os as aios
from typing import Union
import mlx.core as mx
from mlx_lm import load
from exo.helpers import DEBUG
from exo.download.new_shard_download import ensure_downloads_dir


class DummyTokenizer:
  def __init__(self):
    self.eos_token_id = 69
    self.vocab_size = 1000

  def apply_chat_template(self, conversation, tokenize=True, add_generation_prompt=True, tools=None, **kwargs):
    return "dummy_tokenized_prompt"

  def encode(self, text):
    return mx.array([1])

  def decode(self, tokens):
    return "dummy" * len(tokens)


async def resolve_tokenizer(repo_id: Union[str, PathLike]):
  if repo_id == "dummy":
    return DummyTokenizer()
  local_path = await ensure_downloads_dir()/str(repo_id).replace("/", "--")
  if DEBUG >= 2: print(f"Checking if local path exists to load tokenizer from local {local_path=}")
  try:
    if local_path and await aios.path.exists(local_path):
      if DEBUG >= 2: print(f"Resolving tokenizer for {repo_id=} from {local_path=}")
      return await _resolve_tokenizer(local_path)
  except:
    if DEBUG >= 5: print(f"Local check for {local_path=} failed. Resolving tokenizer for {repo_id=} normally...")
    if DEBUG >= 5: traceback.print_exc()
  return await _resolve_tokenizer(repo_id)


async def _resolve_tokenizer(repo_id_or_local_path: Union[str, PathLike]):
  try:
    if DEBUG >= 4: print(f"Loading MLX tokenizer for {repo_id_or_local_path}")
    # MLX-LM's load function returns (model, tokenizer)
    # We only need the tokenizer for this function
    _, tokenizer = load(str(repo_id_or_local_path))
    return tokenizer
  except Exception as e:
    if DEBUG >= 4: print(f"Failed to load MLX tokenizer for {repo_id_or_local_path}. Error: {e}")
    if DEBUG >= 4: print(traceback.format_exc())
    raise ValueError(f"Unsupported model: {repo_id_or_local_path}")
