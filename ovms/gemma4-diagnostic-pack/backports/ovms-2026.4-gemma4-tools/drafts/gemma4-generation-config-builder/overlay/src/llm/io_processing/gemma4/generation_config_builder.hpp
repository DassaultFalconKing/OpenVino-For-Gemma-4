//*****************************************************************************
// Copyright 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//*****************************************************************************
#pragma once
#include "../base_generation_config_builder.hpp"

namespace ovms {

/*
 * Gemma4GenerationConfigBuilder extends BaseGenerationConfigBuilder with Gemma4
 * tool-guided generation (XGrammar / GenAI StructuredOutputConfig).
 *
 * DRAFT: not wired into apply-backport.ps1 or the diagnostic vlm-stable graph.
 * Copy next to gemma4_tool_parser.* and add the factory/BUILD snippets in this folder.
 *
 * Tag mapping follows xgrammar builtin "gemma4" structural tags (PR mlc-ai/xgrammar#588),
 * not the unconstrained native argument dialect `{key:<|"|>value<|"|>}`.
 */
class Gemma4GenerationConfigBuilder : public BaseGenerationConfigBuilder {
public:
    Gemma4GenerationConfigBuilder() = delete;
    explicit Gemma4GenerationConfigBuilder(const ov::genai::GenerationConfig& baseConfig, bool enableToolGuidedGeneration, DecodingMethod decodingMethod) :
        BaseGenerationConfigBuilder(baseConfig, enableToolGuidedGeneration, decodingMethod) {}

    void parseConfigFromRequest(const OpenAIRequest& request) override;
};
}  // namespace ovms
