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

#include <memory>
#include <string>
#include <utility>
#include <openvino/genai/generation_config.hpp>

#include "generation_config_builder.hpp"

namespace ovms {

namespace {
// Keep these identical to Gemma4ToolParser start/end tags and to xgrammar's
// _get_gemma4_structural_tag() constants.
constexpr const char* kToolCallTrigger = "<|tool_call>";
constexpr const char* kToolCallBeginPrefix = "<|tool_call>call:";
constexpr const char* kToolCallEnd = "<tool_call|>";
}  // namespace

void Gemma4GenerationConfigBuilder::parseConfigFromRequest(const OpenAIRequest& request) {
    BaseGenerationConfigBuilder::parseConfigFromRequest(request);

    if (request.toolNameSchemaMap.empty()) {
        return;
    }

    // tool_choice=auto with guided=false: model is unconstrained; parser still
    // converts native markup if the model emits it (TRACE 2026-09-05).
    if (!(enableToolGuidedGeneration || request.toolChoice == "required")) {
        return;
    }

    // xgrammar TagFormat:
    //   begin  = "<|tool_call>call:" + name     // no extra '{'
    //   content = JSONSchema(parameters)        // object INCLUDING braces
    //   end    = "<tool_call|>"
    //   trigger = "<|tool_call>"
    //
    // That guides:
    //   <|tool_call>call:get_weather{"city":"Berlin"}<tool_call|>
    //
    // Unconstrained generation on this checkpoint instead emits native:
    //   <|tool_call>call:get_weather{city:<|"|>Berlin<|"|>}<tool_call|>
    //
    // Do not add '{' to begin if content is JSONSchema — that would yield
    // call:name{{...}}. Do not wrap JSONSchema inside native <|"|> braces.
    // Before shipping, Gemma4ToolParser must accept JSON-after-name as well as
    // the native dialect (see PROMPT.md gate B).
    //
    // Thought tags are NOT added here. The JINJA template already prefixes
    //   <|turn>model\n<|channel>thought\n<channel|>
    // A SequenceFormat thought prefix would fight that empty channel.

    auto triggeredTags = std::make_shared<ov::genai::StructuredOutputConfig::TriggeredTags>();
    triggeredTags->triggers.push_back(kToolCallTrigger);

    for (const auto& [toolName, toolSchemaWrapper] : request.toolNameSchemaMap) {
        const auto& toolSchema = toolSchemaWrapper.stringRepr;
        ov::genai::StructuredOutputConfig::Tag tagItem;
        tagItem.begin = std::string(kToolCallBeginPrefix) + toolName;
        tagItem.end = kToolCallEnd;
        tagItem.content = ov::genai::StructuredOutputConfig::JSONSchema(toolSchema);
        triggeredTags->tags.push_back(tagItem);
    }

    if (request.toolChoice == "required") {
        triggeredTags->at_least_one = true;
    }

    ov::genai::StructuredOutputConfig::StructuralTag structuralTag = triggeredTags;
    setStructuralTagsConfig(structuralTag);
}

}  // namespace ovms
