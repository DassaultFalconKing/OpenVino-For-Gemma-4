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
#include <vector>

#include <openvino/genai/generation_config.hpp>

#include "generation_config_builder.hpp"

namespace ovms {

namespace {
// Keep these identical to Gemma4ToolParser start/end tags.
constexpr const char* kToolCallTrigger = "<|tool_call>";
constexpr const char* kToolCallBeginPrefix = "<|tool_call>call:";
constexpr const char* kToolCallEnd = "<tool_call|>";

using StructuredTag = ov::genai::StructuredOutputConfig::Tag;

std::vector<StructuredTag> buildToolTags(const OpenAIRequest& request) {
    std::vector<StructuredTag> tags;
    tags.reserve(request.toolNameSchemaMap.size());

    for (const auto& [toolName, toolSchemaWrapper] : request.toolNameSchemaMap) {
        StructuredTag tagItem;
        tagItem.begin = std::string(kToolCallBeginPrefix) + toolName;
        tagItem.end = kToolCallEnd;
        tagItem.content = ov::genai::StructuredOutputConfig::JSONSchema(toolSchemaWrapper.stringRepr);
        tags.push_back(std::move(tagItem));
    }

    return tags;
}

bool isHardToolChoice(const std::string& toolChoice) {
    // OpenAIApiHandler normalizes a named tool_choice object to its function
    // name and filters toolNameSchemaMap to that function. Therefore any
    // non-reserved value here is a named forced tool choice.
    return toolChoice == "required" ||
        (!toolChoice.empty() && toolChoice != "auto" && toolChoice != "none");
}
}  // namespace

void Gemma4GenerationConfigBuilder::parseConfigFromRequest(const OpenAIRequest& request) {
    BaseGenerationConfigBuilder::parseConfigFromRequest(request);

    if (request.toolNameSchemaMap.empty()) {
        return;
    }

    // tool_choice=none is stronger than graph-level guided generation. Never
    // re-introduce tools when the caller explicitly disabled them.
    if (request.toolChoice == "none") {
        return;
    }

    const bool hardToolChoice = isHardToolChoice(request.toolChoice);

    // The live 26B probe shows auto tool calling is already healthy. Preserve
    // that path unless the graph explicitly opts into guided generation.
    if (!hardToolChoice && !enableToolGuidedGeneration) {
        return;
    }

    auto toolTags = buildToolTags(request);
    if (toolTags.empty()) {
        return;
    }

    if (hardToolChoice) {
        // IMPORTANT: do not use TriggeredTags here. TriggeredTags only takes
        // control after the model emits <|tool_call> by itself, which still
        // permits prose such as "сейчас запущу" before the call. NovaClaw can
        // interrupt on that prose. A top-level TagsWithSeparator grammar makes
        // the constrained output start with one of the allowed tool tags.
        //
        // For a named tool choice OpenAIApiHandler already leaves only the
        // selected function in toolNameSchemaMap, so this same branch forces
        // exactly the selected tool family without a second selector here.
        auto requiredTags = std::make_shared<ov::genai::StructuredOutputConfig::TagsWithSeparator>();
        requiredTags->tags = std::move(toolTags);
        requiredTags->separator = "";
        requiredTags->at_least_one = true;
        requiredTags->stop_after_first = false;

        ov::genai::StructuredOutputConfig::StructuralTag structuralTag = requiredTags;
        setStructuralTagsConfig(structuralTag);
        return;
    }

    // auto + graph enable_tool_guided_generation=true: keep free-form sampling
    // until Gemma emits the tool trigger, then constrain the selected tool body.
    // This preserves normal content answers while preventing malformed calls.
    auto triggeredTags = std::make_shared<ov::genai::StructuredOutputConfig::TriggeredTags>();
    triggeredTags->triggers.push_back(kToolCallTrigger);
    triggeredTags->tags = std::move(toolTags);
    triggeredTags->at_least_one = false;
    triggeredTags->stop_after_first = false;

    ov::genai::StructuredOutputConfig::StructuralTag structuralTag = triggeredTags;
    setStructuralTagsConfig(structuralTag);
}

}  // namespace ovms
