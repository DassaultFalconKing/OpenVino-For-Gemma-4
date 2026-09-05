[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ModelServerPath
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Get-FileNewline {
    param([Parameter(Mandatory = $true)][string]$Text)
    if ($Text.Contains("`r`n")) { return "`r`n" }
    return "`n"
}

function Normalize-SnippetNewlines {
    param(
        [Parameter(Mandatory = $true)][string]$Snippet,
        [Parameter(Mandatory = $true)][string]$Newline
    )
    $normalized = $Snippet.Replace("`r`n", "`n").Replace("`r", "`n")
    $normalized = $normalized.Replace("`n", $Newline)
    return $normalized.TrimEnd([char]13, [char]10)
}

function Assert-AnchorExactlyOnce {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Anchor,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $count = ([regex]::Matches($Text, [regex]::Escape($Anchor))).Count
    if ($count -ne 1) {
        throw "$Label anchor count is $count; expected exactly 1. Refusing to patch an unexpected OVMS tree."
    }
}

function Insert-BeforeAnchorExactlyOnce {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Anchor,
        [Parameter(Mandatory = $true)][string]$Snippet,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $text = [System.IO.File]::ReadAllText($Path)
    Assert-AnchorExactlyOnce -Text $text -Anchor $Anchor -Label $Label
    $newline = Get-FileNewline -Text $text
    $insert = Normalize-SnippetNewlines -Snippet $Snippet -Newline $newline
    $patched = $text.Replace($Anchor, $insert + $newline + $Anchor)
    [System.IO.File]::WriteAllText($Path, $patched, [System.Text.UTF8Encoding]::new($false))
}

function Insert-AfterAnchorExactlyOnce {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Anchor,
        [Parameter(Mandatory = $true)][string]$Snippet,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $text = [System.IO.File]::ReadAllText($Path)
    Assert-AnchorExactlyOnce -Text $text -Anchor $Anchor -Label $Label
    $newline = Get-FileNewline -Text $text
    $insert = Normalize-SnippetNewlines -Snippet $Snippet -Newline $newline
    $patched = $text.Replace($Anchor, $Anchor + $newline + $insert)
    [System.IO.File]::WriteAllText($Path, $patched, [System.Text.UTF8Encoding]::new($false))
}

$ModelServerPath = (Resolve-Path $ModelServerPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $ModelServerPath ".git"))) {
    throw "ModelServerPath must point to an OVMS source checkout: $ModelServerPath"
}

$overlayRoot = Join-Path $PSScriptRoot "drafts\gemma4-generation-config-builder\overlay"
$overlayHeader = Join-Path $overlayRoot "src\llm\io_processing\gemma4\generation_config_builder.hpp"
$overlaySource = Join-Path $overlayRoot "src\llm\io_processing\gemma4\generation_config_builder.cpp"
foreach ($requiredOverlay in @($overlayHeader, $overlaySource)) {
    if (-not (Test-Path -LiteralPath $requiredOverlay -PathType Leaf)) {
        throw "Gemma4 generation overlay file is missing: $requiredOverlay"
    }
}

$factoryPath = Join-Path $ModelServerPath "src\llm\io_processing\generation_config_builder.hpp"
$buildPath = Join-Path $ModelServerPath "src\llm\BUILD"
$parserPath = Join-Path $ModelServerPath "src\llm\io_processing\gemma4\gemma4_tool_parser.cpp"
$parserTestPath = Join-Path $ModelServerPath "src\test\llm\output_parsers\gemma4_output_parser_test.cpp"
$targetGemmaDir = Join-Path $ModelServerPath "src\llm\io_processing\gemma4"
$targetHeader = Join-Path $targetGemmaDir "generation_config_builder.hpp"
$targetSource = Join-Path $targetGemmaDir "generation_config_builder.cpp"

foreach ($requiredTarget in @($factoryPath, $buildPath, $parserPath, $parserTestPath)) {
    if (-not (Test-Path -LiteralPath $requiredTarget -PathType Leaf)) {
        throw "Expected post-backport OVMS file is missing: $requiredTarget"
    }
}
if (Test-Path -LiteralPath $targetHeader -PathType Leaf) {
    throw "Gemma4 generation builder header already exists; use -SkipApply for an already-patched tree: $targetHeader"
}
if (Test-Path -LiteralPath $targetSource -PathType Leaf) {
    throw "Gemma4 generation builder source already exists; use -SkipApply for an already-patched tree: $targetSource"
}

$backups = @{}
foreach ($path in @($factoryPath, $buildPath, $parserPath, $parserTestPath)) {
    $backups[$path] = [System.IO.File]::ReadAllBytes($path)
}
$createdFiles = New-Object System.Collections.Generic.List[string]

try {
    New-Item -ItemType Directory -Path $targetGemmaDir -Force | Out-Null
    Copy-Item -LiteralPath $overlayHeader -Destination $targetHeader
    $createdFiles.Add($targetHeader)
    Copy-Item -LiteralPath $overlaySource -Destination $targetSource
    $createdFiles.Add($targetSource)

    Insert-AfterAnchorExactlyOnce `
        -Path $factoryPath `
        -Anchor '#include "hermes3/generation_config_builder.hpp"' `
        -Snippet '#include "gemma4/generation_config_builder.hpp"' `
        -Label "GenerationConfigBuilder include"

    $factoryBranch = @'
        } else if (toolParserName == "gemma4") {
            builder_impl = std::make_unique<Gemma4GenerationConfigBuilder>(baseConfig, enableToolGuidedGeneration, decodingMethod);
'@
    Insert-BeforeAnchorExactlyOnce `
        -Path $factoryPath `
        -Anchor '        } else if (toolParserName == "phi4") {' `
        -Snippet $factoryBranch `
        -Label "GenerationConfigBuilder gemma4 factory branch"

    Insert-AfterAnchorExactlyOnce `
        -Path $buildPath `
        -Anchor '            "io_processing/hermes3/generation_config_builder.hpp",' `
        -Snippet '            "io_processing/gemma4/generation_config_builder.hpp",' `
        -Label "generation_config_builders hdrs"

    Insert-AfterAnchorExactlyOnce `
        -Path $buildPath `
        -Anchor '            "io_processing/hermes3/generation_config_builder.cpp",' `
        -Snippet '            "io_processing/gemma4/generation_config_builder.cpp",' `
        -Label "generation_config_builders srcs"

    # Hard required/named generation uses JSONSchema inside the Gemma4 tool tag.
    # Preserve native {key:<|"|>value<|"|>} parsing, but fast-path a complete
    # ordinary JSON object when the grammar generated one.
    $guidedJsonParser = @'

    const std::string guidedArguments = "{" + argumentsStr + "}";
    rapidjson::Document guidedArgsDoc;
    guidedArgsDoc.Parse(guidedArguments.c_str());
    if (!guidedArgsDoc.HasParseError() && guidedArgsDoc.IsObject()) {
        rapidjson::StringBuffer guidedArgsBuffer;
        rapidjson::Writer<rapidjson::StringBuffer> guidedArgsWriter(guidedArgsBuffer);
        guidedArgsDoc.Accept(guidedArgsWriter);
        this->toolCall.arguments = guidedArgsBuffer.GetString();
        this->currentState = State::ToolCallEnded;
        this->streamingPosition = pos + TOOL_ARGS_END_INDICATOR.length();
        SPDLOG_LOGGER_TRACE(llm_calculator_logger, "Parsed Gemma4 guided JSON arguments directly: {}", this->toolCall.arguments);
        return true;
    }
'@
    Insert-AfterAnchorExactlyOnce `
        -Path $parserPath `
        -Anchor '    SPDLOG_LOGGER_TRACE(llm_calculator_logger, "Parsed arguments string: {}", argumentsStr);' `
        -Snippet $guidedJsonParser `
        -Label "Gemma4 guided JSON parser fast path"

    $guidedJsonTest = @'
TEST_F(Gemma4OutputParserTest, ParseToolCallOutputWithGuidedJsonArguments) {
    const std::string input = R"JSON(<|tool_call>call:example_tool{"arg1":"value1","arg2":42,"nested":{"enabled":true},"paths":["C:\\llm\\ovms.exe","C:\\llm\\README.md"]}<tool_call|>)JSON";

    auto generatedTensor = gemma4Tokenizer->encode(input).input_ids;
    std::vector<int64_t> generatedTokens(generatedTensor.data<int64_t>(), generatedTensor.data<int64_t>() + generatedTensor.get_size());
    ParsedOutput parsedOutput = ovms::test::parseWithStreamer(*gemma4Tokenizer, *outputParserWithRegularToolParsing, generatedTokens, true, true);

    EXPECT_EQ(parsedOutput.content, "");
    EXPECT_EQ(parsedOutput.reasoning, "");
    ASSERT_EQ(parsedOutput.toolCalls.size(), 1);
    EXPECT_EQ(parsedOutput.toolCalls[0].name, "example_tool");
    EXPECT_EQ(
        parsedOutput.toolCalls[0].arguments,
        R"JSON({"arg1":"value1","arg2":42,"nested":{"enabled":true},"paths":["C:\\llm\\ovms.exe","C:\\llm\\README.md"]})JSON");
    EXPECT_FALSE(parsedOutput.toolCalls[0].id.empty());
}

'@
    Insert-BeforeAnchorExactlyOnce `
        -Path $parserTestPath `
        -Anchor 'TEST_F(Gemma4OutputParserTest, ParseToolCallOutputWithSingleToolCallAndReasoning) {' `
        -Snippet $guidedJsonTest `
        -Label "Gemma4 guided JSON regression test"

    $relativePaths = @(
        "src/llm/io_processing/gemma4/generation_config_builder.hpp",
        "src/llm/io_processing/gemma4/generation_config_builder.cpp",
        "src/llm/io_processing/generation_config_builder.hpp",
        "src/llm/BUILD",
        "src/llm/io_processing/gemma4/gemma4_tool_parser.cpp",
        "src/test/llm/output_parsers/gemma4_output_parser_test.cpp"
    )
    Push-Location $ModelServerPath
    try {
        & git add -- @relativePaths
        if ($LASTEXITCODE -ne 0) {
            throw "git add failed while staging the local Gemma4 generation overlay"
        }
    } finally {
        Pop-Location
    }

    Write-Host "Gemma4 hard tool-choice generation overlay integrated:"
    Write-Host "  auto + guided=false: native unconstrained path preserved"
    Write-Host "  auto + guided=true: TriggeredTags"
    Write-Host "  required / named: top-level TagsWithSeparator"
    Write-Host "  parser: native Gemma4 + guided JSON argument dialects"
} catch {
    foreach ($entry in $backups.GetEnumerator()) {
        [System.IO.File]::WriteAllBytes($entry.Key, $entry.Value)
    }
    foreach ($created in $createdFiles) {
        if (Test-Path -LiteralPath $created) {
            Remove-Item -LiteralPath $created -Force
        }
    }
    throw
}
