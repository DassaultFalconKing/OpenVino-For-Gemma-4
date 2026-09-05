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
 * tool-guided generation using OpenVINO GenAI StructuredOutputConfig.
 *
 * DRAFT: not wired into apply-backport.ps1 or the diagnostic vlm-stable graph.
 * Copy next to gemma4_tool_parser.* and add the factory/BUILD snippets in this folder.
 *
 * Policy:
 *   - auto + guided=false: leave decoding unconstrained (live probe is healthy)
 *   - auto + guided=true: TriggeredTags constrains a call after the model emits
 *     the <|tool_call> trigger
 *   - required / named tool_choice: top-level TagsWithSeparator(at_least_one)
 *     constrains decoding from the first generated token
 *   - none: never installs a tool grammar
 *
 * Tool bodies use JSONSchema content. Gemma4ToolParser must therefore accept
 * both native <|\"|>-quoted arguments and guided standard-JSON arguments before
 * this builder is enabled in a runtime.
 */
class Gemma4GenerationConfigBuilder : public BaseGenerationConfigBuilder {
public:
    Gemma4GenerationConfigBuilder() = delete;
    explicit Gemma4GenerationConfigBuilder(const ov::genai::GenerationConfig& baseConfig, bool enableToolGuidedGeneration, DecodingMethod decodingMethod) :
        BaseGenerationConfigBuilder(baseConfig, enableToolGuidedGeneration, decodingMethod) {}

    void parseConfigFromRequest(const OpenAIRequest& request) override;
};
}  // namespace ovms
