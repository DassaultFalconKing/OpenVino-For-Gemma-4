# Source notes

Configuration choices in this pack are based on:

- OpenVINO Model Server current LLM calculator schema:
  https://github.com/openvinotoolkit/model_server/blob/main/src/llm/llm_calculator.proto
- OVMS LLM serving reference:
  https://github.com/openvinotoolkit/model_server/blob/main/docs/llm/reference.md
- OVMS troubleshooting guidance for switching preview/new models from continuous batching to stateful pipelines:
  https://github.com/openvinotoolkit/model_server/blob/main/docs/troubleshooting.md
- Wondernuttz Gemma-4 quickstart and reference server:
  https://github.com/Wondernuttz/OpenVino-For-Gemma-4/blob/main/QUICKSTART.md
  https://github.com/Wondernuttz/OpenVino-For-Gemma-4/blob/main/serving/ovserver_moe.py

The Wondernuttz reference server uses VLMPipeline with
DYNAMIC_QUANTIZATION_GROUP_SIZE=0 and serializes generation for the 26B MoE.
