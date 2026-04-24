"""
Hugo Blog Post Translator using OpenAI Agents SDK
Translates Papermod themed blog posts using agent-based architecture
"""

import yaml
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from openai import OpenAI
from dataclasses import dataclass, field
from io_google_spreadsheet import read_from_google_spreadsheet
import json
import argparse
import config
import time
import uuid
import random
import os

from utils import send_metrics
from config import Stats


# ============================================================================
# TOKEN TRACKING DATACLASSES
# ============================================================================

@dataclass
class TokenUsage:
    """Token usage from a single LLM call"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


@dataclass
class TokenTracker:
    """Accumulates token usage across multiple LLM calls"""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_calls: int = 0
    calls: List[Dict] = field(default_factory=list)

    def record(self, usage: TokenUsage, call_purpose: str = "") -> None:
        """Record token usage from a single LLM call"""
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.total_calls += 1
        self.calls.append({
            "purpose": call_purpose,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "model": usage.model,
        })

    def reset(self) -> None:
        """Reset all counters (use between posts)"""
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_calls = 0
        self.calls = []

    def summary(self) -> str:
        return (
            f"📊 Token Usage: {self.total_prompt_tokens} prompt + "
            f"{self.total_completion_tokens} completion = "
            f"{self.total_tokens} total tokens across {self.total_calls} LLM calls"
        )


# ============================================================================
def call_openai(client: OpenAI, system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = None, model: str = config.PROFESSIONALIZE_LLM_MODEL) -> Tuple[str, TokenUsage]:
    """
    Unified function to call OpenAI API with customizable prompts and parameters.

    Args:
        client: OpenAI client instance
        system_prompt: System message content
        user_prompt: User message content
        temperature: Sampling temperature (default 0.3)
        max_tokens: Maximum tokens in response (optional)
        model: Model to use (default "recommended")

    Returns:
        Tuple of (stripped response content, TokenUsage)
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    kwargs = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**kwargs)
    # print(f"   🤖 OpenAI Response:\n{response}")

    usage = TokenUsage(
        prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
        completion_tokens=response.usage.completion_tokens if response.usage else 0,
        total_tokens=response.usage.total_tokens if response.usage else 0,
        model=response.model,
    )
    print("="*40)
    print(f"== ⚠️ ==	prompt_tokens	completion_tokens	total_tokens	model	{usage.prompt_tokens}	{usage.completion_tokens}	{usage.total_tokens}	{usage.model}")
    print("="*40)


    text = (response.choices[0].message.content or "").strip()
    return text, usage

@dataclass
class TranslationConfig:
    """Configuration for translation settings"""
    translatable_fields = [
        'title', 
        'seoTitle',
        'description', 
        'summary', 
        'cover.alt',
        'cover.caption',
        'steps',
        'faqs'
    ]

    # Product name examples for prompt (not translated)
    product_examples = [
        "Aspose.PDF for .NET",
        "Aspose.Words for Python via .NET",
        "GroupDocs.Comparison for Node.js",
        "Aspose.Cells for Node.js via Java",
        "Conholdate.Total for .NET",
    ]

    # Supported target languages
    supported_languages = [
        'ar',  # Arabic
        'cs',  # Czech
        'de',  # German
        'es',  # Spanish
        'fr',  # French
        'it',  # Italian
        'ja',  # Japanese
        'ko',  # Korean
        'nl',  # Dutch
        'pl',  # Polish
        'pt',  # Portuguese
        'ru',  # Russian
        'tr',  # Turkish
        'zh',  # Chinese
        'vi',  # Vietnamese
        'id',  # Indonesian
        'th',  # Thai
        'el',  # Greek
        'sv',  # Swedish
        'da',  # Danish
        'no',  # Norwegian
        'fi',  # Finnish
    ]

    # Language names for display
    language_names = {
        'ar': 'Arabic',
        'cs': 'Czech',
        'de': 'German',
        'es': 'Spanish',
        'fr': 'French',
        'it': 'Italian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'nl': 'Dutch',
        'pl': 'Polish',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'tr': 'Turkish',
        'zh': 'Chinese',
        'vi': 'Vietnamese',
        'id': 'Indonesian',
        'th': 'Thai',
        'el': 'Greek',
        'sv': 'Swedish',
        'da': 'Danish',
        'no': 'Norwegian',
        'fi': 'Finnish',
    }
    GIT_REPO_ASPOSE_COM         = "blog-checkedout-repo/content/Aspose.Blog"
    GIT_REPO_GROUPDOCS_COM      = "blog-checkedout-repo/content/Groupdocs.Blog"
    GIT_REPO_CONHOLDATE_COM     = "blog-checkedout-repo/content/Conholdate.Total"
    GIT_REPO_ASPOSE_CLOUD       = "blog-checkedout-repo/content/Aspose.Cloud"
    GIT_REPO_GROUPDOCS_CLOUD    = "blog-checkedout-repo/content/GroupDocs.Cloud"
    GIT_REPO_CONHOLDATE_CLOUD   = "blog-checkedout-repo/content/Conholdate.Cloud"

    domain_map = {
    "blog.aspose.com"       : "Aspose.Blog",
    "blog.groupdocs.com"    : "Groupdocs.Blog",
    "blog.conholdate.com"   : "Conholdate.Total",
    "blog.aspose.cloud"     : "Aspose.Cloud",
    "blog.groupdocs.cloud"  : "GroupDocs.Cloud",
    "blog.conholdate.cloud" : "Conholdate.Cloud",
    }

# ============================================================================
# TOOLS - Functions that agents can call
# ============================================================================

def parse_markdown_file(file_path: str) -> Dict[str, Any]:
    """
    Tool: Parse a markdown file into frontmatter and content
    
    Args:
        file_path: Path to the markdown file
        
    Returns:
        Dictionary with 'frontmatter' and 'content' keys
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split frontmatter and content
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        raise ValueError("Invalid markdown format: frontmatter not found")
    
    frontmatter_str = match.group(1)
    post_content = match.group(2)
    
    # Parse YAML frontmatter
    frontmatter = yaml.safe_load(frontmatter_str)
    
    return {
        'frontmatter': frontmatter,
        'content': post_content
    }


def write_markdown_file(file_path: str, frontmatter: Dict[str, Any], content: str) -> Dict[str, str]:
    """
    Tool: Write frontmatter and content to a markdown file
    
    Args:
        file_path: Output file path
        frontmatter: Frontmatter dictionary
        content: Post content
        
    Returns:
        Status message
    """
    # Convert frontmatter back to YAML
    frontmatter_str = yaml.dump(
        frontmatter, 
        allow_unicode=True, 
        sort_keys=False,
        default_flow_style=False
    )
    
    # Combine and write
    full_content = f"---\n{frontmatter_str}---\n\n{content}"
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    return {"status": "success", "file": file_path}


# Product names protection removed - handled in prompts instead


def update_url_with_language(url: str, lang_code: str) -> str:
    """
    Tool: Add language prefix to URL
    
    Args:
        url: Original URL
        lang_code: Language code (e.g., 'es', 'fr')
        
    Returns:
        Updated URL with language prefix
    """
    if not url.startswith(f'/{lang_code}/'):
        return f'/{lang_code}{url}'
    return url


# ============================================================================
# AGENTS - Specialized agents for different tasks
# ============================================================================

class FrontmatterTranslatorAgent:
    """Agent responsible for translating frontmatter fields"""
    
    def __init__(self, client: OpenAI, config: TranslationConfig):
        self.client = client
        self.config = config
        self.name = "FrontmatterTranslator"
        self.token_tracker: Optional[TokenTracker] = None
    
    def get_nested_value(self, data: Dict, key_path: str) -> Any:
        """Get value from nested dictionary using dot notation"""
        keys = key_path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value
    
    def set_nested_value(self, data: Dict, key_path: str, value: Any):
        """Set value in nested dictionary using dot notation"""
        keys = key_path.split('.')
        current = data
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def translate(self, domain:str, frontmatter: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
        """
        Translate frontmatter fields
        
        Args:
            frontmatter: Original frontmatter
            target_lang: Target language code
            
        Returns:
            Translated frontmatter
        """
        translated_fm = frontmatter.copy()
        
        for field in self.config.translatable_fields:
            value = self.get_nested_value(frontmatter, field)
            
            if value is None:
                continue
            
            # Handle different field types
            if isinstance(value, str):
                translated_value = self._translate_text(value, target_lang)
                self.set_nested_value(translated_fm, field, translated_value)
            
            elif isinstance(value, list):
                translated_list = self._translate_list(value, target_lang)
                self.set_nested_value(translated_fm, field, translated_list)
        
        # Update URL
        if 'url' in translated_fm:
            translated_fm['url'] = update_url_with_language(
                translated_fm['url'], 
                target_lang
            )
        
        return translated_fm
    
    def _translate_list(self, items: List, target_lang: str) -> List:
        """Translate list items (steps, FAQs, etc.)"""
        translated_list = []
        
        for item in items:
            if isinstance(item, str):
                translated = self._translate_text(item, target_lang)
                translated_list.append(translated)
            
            elif isinstance(item, dict):
                # For FAQs with q/a structure
                translated_item = {}
                for k, v in item.items():
                    if isinstance(v, str):
                        translated_item[k] = self._translate_text(v, target_lang)
                    else:
                        translated_item[k] = v
                translated_list.append(translated_item)
            else:
                translated_list.append(item)
        
        return translated_list
    
    def _translate_text(self, text: str, target_lang: str) -> str:
        """Use OpenAI to translate text"""
        
        # Build product examples string
        product_examples = "\n".join([f"  - {p}" for p in self.config.product_examples])

        prompt = f"""Translate the following text to {self.config.language_names.get(target_lang, "")} language with code '{target_lang}'.

            CRITICAL RULES:
            1. DO NOT translate product names like:
            {product_examples}
            Keep them EXACTLY as they appear (including "for .NET", "via Python", etc.)

            2. Maintain the same tone and style
            3. Keep technical terms accurate
            4. Preserve any URLs or file paths
            5. Provide ONLY the translation, no explanations.
            6. Do NOT add any additional formatting markers or identifier like ```markdown``` at the start or end of the translated content.

            Below is the Text to translate:
            {text}

            """

        # ============================================================================
        # print(f"\n📋 Frontmatter Translating: ({text})...")
        # ============================================================================

        translated, usage = call_openai(
            self.client,
            "You are a professional technical translator specializing in software documentation. You NEVER translate product names like Aspose, GroupDocs, or Conholdate products.",
            prompt,
            temperature=0.3
        )
        if self.token_tracker:
            self.token_tracker.record(usage, "frontmatter_translate")
        # print(f"📋 Frontmatter Translated: ({translated})...")
        # print(f"{'='*60}")

        return translated


class ContentTranslatorAgent:
    """Agent responsible for translating markdown content"""
    
    def __init__(self, client: OpenAI, config: TranslationConfig):
        self.client = client
        self.config = config
        self.name = "ContentTranslator"
        self.token_tracker: Optional[TokenTracker] = None
    
    def translate(self, domain:str, content: str, target_lang: str) -> str:
        """
        Translate markdown content while preserving formatting
        
        Args:
            content: Original markdown content
            target_lang: Target language code
            
        Returns:
            Translated content
        """
        return self._translate_markdown(domain, content, target_lang)
    
    def _translate_markdown(self, domain:str, content: str, target_lang: str) -> str:
        """Use OpenAI to translate markdown content with chunking for long content"""

        # Split content into paragraphs (chunks)
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

        if len(paragraphs) <= 1:
            # Single paragraph or empty content - translate directly
            return self._translate_content_chunk(content, target_lang)

        # Multiple paragraphs - translate each as a separate chunk
        print(f"📝 Content has {len(paragraphs)} paragraphs, translating chunk by chunk...")

        
        code_block = False
        translated_chunks = []
        combined_paragraph = ""
        i = 0
        n = len(paragraphs)

        while i < n:
            paragraph = paragraphs[i]    
            print(f"   📝 Translating paragraph {i+1}/{len(paragraphs)} : {paragraph.replace("\n", "")[:20]}...", end=" : ", flush=True)
            
            # if paragraph starts with ``` and does not ends with ```, then it's a code block start
            # so keep adding next paragraphs until we find the ending ```
            if paragraph.strip().startswith('```') and not paragraph.strip().endswith('```'):
                code_block = True
                combined_paragraph += paragraph + "\n\n"
                i += 1
                while i < n and code_block:
                    next_paragraph = paragraphs[i]
                    combined_paragraph += next_paragraph + "\n\n"

                    # check if code block ends here
                    if next_paragraph.strip().endswith("```"):
                        code_block = False
                        break

                    i += 1

                paragraph = combined_paragraph.strip()
                print(f"Combined Paragraphs:{paragraph}")
                combined_paragraph = ""

            translated_chunk = self._translate_content_chunk(domain, paragraph, target_lang)
            translated_chunks.append(translated_chunk)
            i += 1

        # Combine translated chunks
        final_content = '\n\n'.join(translated_chunks)
        print(f"   ✓ Combined {len(translated_chunks)} translated paragraphs")

        return final_content

    def _translate_content_chunk(self, domain:str, chunk: str, target_lang: str, max_retries: int = 3) -> str:
        """Translate a single chunk of markdown content with retry logic"""
        print(f"   🔄 Translating chunk...")
        # Check if this chunk should skip translation validation (code blocks, shortcodes)
        should_skip_validation = self._should_skip_translation_validation(chunk)
        # print(f"   🔍 Should skip validation: {should_skip_validation}")

        # Build product examples string
        product_examples = "\n".join([f"  - {p}" for p in self.config.product_examples])

        CRITICAL_RULES = f"""
                CRITICAL RULES:
                1. DO NOT translate product names like:
                {product_examples}
                Keep them EXACTLY as they appear (including "for .NET", "via Python", etc.)

                2. Preserve ALL markdown formatting (headers, links, code blocks, images, bold, italic)

                3. Do NOT translate:
                    - Code blocks (inside ``` ```)
                    - URLs and file paths
                    - Image paths
                    - Code variable names or function names
                    - API endpoints

                4. Maintain the same structure and formatting
                5. If a URL contains domain name "{domain}", add language code "{target_lang}" at the end of URL
                    - (e.g., turn such urls (https://{domain}/cells/<rest of URL>/) to this (https://{domain}/{target_lang}/cells/<rest of URL>) )
                6. Do NOT include any markers or identifier like ```markdown``` at the start or end of the translated content.
                7. Keep the same tone and style
                8. Keep technical terms accurate
                9. Provide ONLY the translated markdown, no explanations or preamble is needed.
                10. If the provided content seems empty or just contain markdown formatting, return the content as it is.
                11. Ensure the translated content should not result in any markdown parsing errors.
                12. If the values of attributes in shortcodes contain double quotes (") then escape the internal quotes using (\\")
        """


        for attempt in range(max_retries):

            # Create prompt based on attempt number
            if attempt == 0:
                # First attempt - normal prompt
                prompt = f"""Translate the provided markdown content to {self.config.language_names.get(target_lang, "")} language having code '{target_lang}'.
                
                CRITICAL_RULES to follow:
                {CRITICAL_RULES}

                YOU ONLY HAVE TO TRANSLATE THE BELOW CONTENT COMPLETELY. Do not return the original text.

                Below is the Markdown content to translate:
                {chunk}"""
            else:            
                # Retry attempts - stronger prompt (only if not skipping validation)
                if should_skip_validation:
                    break  # Don't retry for code blocks/shortcodes
    
                print(f"   🔄 Translation attempt {attempt + 1}/{max_retries}...")

                prompt = f"""IMPORTANT: This is RETRY ATTEMPT #{attempt + 1}. The previous translation returned untranslated content.

                    Translate the provided markdown content to {self.config.language_names.get(target_lang, "")} language with code '{target_lang}'. You MUST translate it completely.

                    CRITICAL_RULES to follow:
                    {CRITICAL_RULES}

                    YOU ONLY HAVE TO TRANSLATE THE BELOW CONTENT COMPLETELY. Do not return the original text.

                    Below is the Markdown content to translate:
                    {chunk}

                    """

                print(f"Retrying Translation for:\n{chunk}")

            translated_chunk, usage = call_openai(
                self.client,
                "You are a professional technical translator specializing in markdown documentation. You NEVER translate product names like Aspose, GroupDocs, or Conholdate products. You preserve all code, URLs, and technical references exactly as they are.",
                prompt,
                temperature=0.3
            )
            if self.token_tracker:
                self.token_tracker.record(usage, "content_translate")


            # Check if translation was successful
            if should_skip_validation:
                # print(f"   should_skip_validation is True")
                # Skip validation for code blocks/shortcodes - accept as successful
                if attempt > 0:
                    print(f"   ✓ Translation successful on attempt {attempt + 1} (skipped validation)")
                
                print(f"   -- Skip validation -- >>{translated_chunk.replace("\n", "")[:20]}")

                return translated_chunk

            

            # For regular content, check if translation succeeded
            if self._appears_translated(chunk, translated_chunk):
                # print(f"   ✅ Appears Translated")
                if attempt > 0:
                    print(f"   ✓ Translation successful on attempt {attempt + 1}")
                return translated_chunk
            else:
                print(f"   ❌ Does Not Appears Translated")
                # Translation appears to have failed - analyze with AI
                print(f"   ⚠️  Translation attempt {attempt + 1} appears untranslated, analyzing with AI...")
                if self._ai_should_retry(chunk, translated_chunk,target_lang):
                    print(f"   🔄 AI determined content should be RE-TRIED for translation.")
                    if attempt == max_retries - 1:
                        print(f"   ❌ All {max_retries} attempts failed, returning original chunk")
                        return chunk  # Return original if all retries fail
                    # Continue to next attempt
                else:
                    print(f"   ✅ AI determined untranslated content is acceptable (code/technical)")
                    return translated_chunk  # Accept as successful

        return chunk  # Fallback

    def _appears_translated(self, original: str, translated: str) -> bool:
        """Quick check if translation appears successful using heuristics"""
        import re

        # Clean texts for comparison
        def clean_text(text):
            text = re.sub(r'[*_`#]', '', text)  # Remove markdown
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # Remove links
            text = re.sub(r'```[^\n]*\n.*?```', '', text, flags=re.DOTALL)  # Remove code blocks
            text = re.sub(r'`[^`]*`', '', text)  # Remove inline code
            text = re.sub(r'\s+', ' ', text).strip()
            return text.lower()

        original_clean = clean_text(original)
        translated_clean = clean_text(translated)

        # print(f"   Comparing cleaned texts:\nOriginal: {original_clean}\nTranslated: {translated_clean}")

        # If identical after cleaning, not translated
        if original_clean == translated_clean:
            # print(f"  ⚠️  Identical after cleaning")
            return False

        # Check for minimum word change (simple heuristic)
        original_words = set(original_clean.split())
        translated_words = set(translated_clean.split())

        if len(original_words) <= 2:  # Very short text
            print(f"   Short Text -- >>{translated.replace("\n", "")[:20]}")
            return len(translated_words) > 0

        changed_words = len(original_words - translated_words)
        # changed_words = len(translated_words - original_words)
        change_percent = changed_words / len(original_words)*100

        # print(f"   Changed words: {changed_words}")
        # print(f"   Original words: {original_words}")
        # print(f"   Translated words: {translated_words}")
        print(f"   Changed words %: {change_percent:.0f}% -- >>{translated.replace("\n", "")[:20]}")

        return change_percent > 20  # Lower threshold for quick check

    def _ai_should_retry(self, original: str, translated: str, target_lang:str) -> bool:
        """Ask AI to analyze if untranslated content should be retried"""
        analysis_result = self._analyze_translation_validity(original, translated, target_lang)
        return analysis_result == 'RETRY'


    def _analyze_translation_validity(self, original: str, translated: str, target_lang: str) -> str:
        """Ask AI to analyze if translation failure is valid"""

        analysis_prompt = f"""
        Analyze this translation and determine if the TRANSLATED TEXT is translated in {self.config.language_names.get(target_lang, "")} language with code '{target_lang}'.
        If the TRANSLATED TEXT is not translated then you should determine if it should be translated or it is OK to keep it remain untranslated.

        ORIGINAL TEXT:
        {original}

        TRANSLATED TEXT:
        {translated}

        INSTRUCTIONS:
        - Return only 'VALID' if the translation result is acceptable because the content should not be translated (code, technical terms, proper names, etc.)
        - Return 'VALID' if it is markdown formatting, code blocks, URLs, technical terminology, or product names.
        - Return only 'RETRY' if this content should have been translated but the result appears untranslated or incorrect
        - Be conservative: if in doubt, return 'RETRY'

        RESPONSE FORMAT:
        Do not provide explanations. Provide only one word as the final answer: VALID or RETRY.
        """
        print(f"   🤖 Analyzing translation validity with AI...")
        # print(f"   🤖 Prompt: {analysis_prompt}")
        try:
            response, usage = call_openai(
                self.client,
                "You are an expert translation quality analyst specializing in technical documentation and code.",
                analysis_prompt,
                temperature=0.1,  # Low temperature for consistent analysis
                # max_tokens=10     # Very short response needed
            )
            if self.token_tracker:
                self.token_tracker.record(usage, "translation_validity_check")
            # print(f"   🤖 AI Analysis Response: {response}")

            result = response.strip().upper()
            if result in ['VALID', 'RETRY']:
                return result
            else:
                print(f"   ⚠️  Unexpected AI analysis response: {result}, defaulting to RETRY")
                return 'RETRY'

        except Exception as e:
            print(f"   ❌ AI analysis failed: {e}, defaulting to RETRY")
            return 'RETRY'

    def _should_skip_translation_validation(self, chunk: str) -> bool:
        """Check if a chunk should skip translation validation (code blocks, shortcodes, etc.)"""
        chunk_stripped = chunk.strip()

        # Skip if it's a code block (starts or ends with ```)
        if chunk_stripped.startswith('```') or chunk_stripped.endswith('```'):
            return True

        if chunk_stripped == '---':
            return True

        # Skip if it contains markdown shortcodes
        if '{{<' in chunk_stripped and '>}}' in chunk_stripped:
            return True

        return False

# ============================================================================
# PLATFORM IDENTIFIER AGENT - Identifies the platform of a blog post
# ============================================================================
class PlatformIdentifierAgent:
    """Agent responsible for identifying the platform of a blog post"""

    def __init__(self, client: OpenAI, config: TranslationConfig):
        self.client = client
        self.config = config
        self.name = "PlatformIdentifier"
        self.token_tracker: Optional[TokenTracker] = None

    def identify_platform(self, content: str) -> str:
        """
        Identify the platform from the blog post content using OpenAI

        Args:
            content: Full content (frontmatter + content) of the markdown file

        Returns:
            Identified platform string
        """
        platforms_list = ", ".join(config.PLATFORMS)

        prompt = f"""Analyze the following blog post content (that is in markdown format) and identify the primary platform it is about.

Available platforms: {platforms_list}

Instructions:
- Look for mentions of programming languages, frameworks, or technologies that match the platforms.
- If the content matches ONE of the available platforms exactly, return that ONE platform.
- If it doesn't match any, return "ALL".
- If content matched multiple platforms, return the word "ALL". Forexample: if content show examples of both C# .NET and Java, return "ALL".
- If content explains online tool approach of a feature then also describes the developer way(s) to achieve it, return "ALL".
- If content show examples of C# .NET but just slightly mentions that this feature is also available in Java or any other API(s), return ".NET" as .NET is the main platform, major focus, and main subject of the blog post.
- Return only the ONE platform name, nothing else.
- There is no Unknown platform, if you can't identify, return "ALL".

Blog post content:
{content}
"""

        try:
            identified_platform, usage = call_openai(
                self.client,
                "You are an expert at identifying software platforms and technologies from technical content.",
                prompt,
                temperature=0.1  # Low temperature for consistent classification
            )
            if self.token_tracker:
                self.token_tracker.record(usage, "platform_identify")
            return identified_platform.strip()
        except Exception as e:
            print(f"   ❌ Error identifying platform: {e}")
            return "Unknown"


# ============================================================================
# ORCHESTRATOR - Coordinates agents to complete translation task
# ============================================================================

class TranslationOrchestrator:
    """
    Orchestrates the translation workflow using specialized agents
    """
    
    def __init__(self, api_key: str = None):
        self.client = OpenAI(
            api_key=api_key,
            base_url=config.PROFESSIONALIZE_BASE_URL
        )
        self.config = TranslationConfig()

        # Shared token tracker (reset per post inside translate_files)
        self.token_tracker = TokenTracker()

        # Initialize specialized agents and wire up the shared tracker
        self.frontmatter_agent = FrontmatterTranslatorAgent(self.client, self.config)
        self.frontmatter_agent.token_tracker = self.token_tracker

        self.content_agent = ContentTranslatorAgent(self.client, self.config)
        self.content_agent.token_tracker = self.token_tracker

        self.platform_agent = PlatformIdentifierAgent(self.client, self.config)
        self.platform_agent.token_tracker = self.token_tracker
    
    # ============================================================================
    # TRANSLATE ALL FILES IN ALL MISSING LANGUAGES
    # ============================================================================
    def translate_files(self, 
                        currentDomain=None, 
                        target_author=None, 
                        translation_limit=None, 
                        posts_list_to_translate: List[List[Any]]=None):

        missing_translations_stats = Stats(0, 0, 0, 0)
        total_start_time = time.time()
        total_status = "success"

        print(f"   Translating {len(posts_list_to_translate)} Items")

        for item in posts_list_to_translate:

            # Reset token tracker for each post so metrics are per-post
            self.token_tracker.reset()
 
            start_time = time.time()
            status = "success"
            
            items_discovered = 0
            items_succeeded = 0
            items_failed = 0
            items_skipped = 0
            
            discovery_list = []
            failure_list = []
            success_list = []
            skipped_list = []

            try:

                domain = item[0]
                product = item[1]
                slug = item[2]
                post_url = item[3]
                post_author = item[4]
                missed_langs = discovery_list = [x.strip() for x in item[6].split(',')]

                print(f"✅ Translating: {item}")
                print(f"\n{'='*60}")
                print(f"{product}\t>\t{slug}\tby\t>\t{post_author}\tinto\t{item[6]}")
                print(f"\n{'='*60}")

                missing_translations_stats.items_discovered += len(missed_langs)
                items_discovered += len(missed_langs)

                blog_main_repo = self.config.domain_map.get(domain)

                if not blog_main_repo:
                    raise ValueError(f"Unknown domain Provided: {currentDomain}")

                input_path = f"blog-checkedout-repo/content/{blog_main_repo}/{product}/{slug}"
                index_md_file_path = f"{input_path}/index.md"

                print(f"Input Path {input_path}")
                print(f"Input File Path {index_md_file_path}")

                # ============================================================================
                # Identify platform
                # ============================================================================
                parsed = parse_markdown_file(index_md_file_path)
                frontmatter = parsed['frontmatter']
                post_content = parsed['content']
                full_content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)}---\n\n{post_content}"
                identified_platform = self.platform_agent.identify_platform(full_content)
                print(f"   🏷️  Identified Platform: {identified_platform}")
                # ============================================================================

                for missed_lang in missed_langs:
                    try:
                        missed_lang = missed_lang.strip()

                        # if input_path/index.{missed_lang}.md exists, skip
                        output_file_path = f"{input_path}/index.{missed_lang}.md"
                        if Path(output_file_path).exists() or not missed_lang:
                            print(f"⚠️  Skipping translation for {slug} into '{missed_lang}' as it already exists.")
                            items_skipped += 1
                            missing_translations_stats.items_skipped += 1
                            skipped_list.append(missed_lang)
                            continue

                        print(f"✅ Translating: {slug} into {missed_lang}...")

                        translation_file_path = self.translate_file(index_md_file_path, missed_lang, domain)
                        # translation_file_path = None 

                        if translation_file_path:
                            missing_translations_stats.items_succeeded += 1
                            items_succeeded +=1
                            success_list.append(missed_lang)

                    except Exception as e:
                        msg = str(e)

                        # Detect 401 authentication error
                        if "401" in msg or "Authentication Error" in msg or "token_not_found_in_db" in msg:
                            print("❌ Authentication failed. CHECK YOUR KEY...")
                            print("❌ Error:"+ msg)
                            sys.exit(1)

                        print(f"❌ Error translating {index_md_file_path} to {missed_lang}: {e}\n")
                        continue
                
                end_time = time.time()
                run_duration_ms = int((end_time - start_time) * 1000)
                run_id = str(uuid.uuid4())

                items_failed = items_discovered - items_succeeded
                if items_failed > 0:
                    failure_list = [item for item in discovery_list if item not in success_list]

                # Print and capture token usage summary for this post
                print(f"\n{self.token_tracker.summary()}")

                send_metrics(    run_id,
                        status,
                        run_duration_ms,
                        agent_name          = config.AGENT_BLOG_POST_TRANSLATOR,
                        job_type            = config.JOB_TYPE_TRANSLATION,
                        item_name           = config.JOB_ITEM_TRANSLATIONS_ADDED,
                        items_discovered    = items_discovered,
                        items_failed        = items_failed,
                        items_succeeded     = items_succeeded,
                        items_skipped       = items_skipped,
                        product             = config.PRODUCT_MAP[currentDomain][product] if product else config.NOT_APPLICABLE,
                        platform            = identified_platform,
                        website             = domain.replace("blog.", ""),
                        post_dir            = slug,
                        post_url            = post_url,
                        post_author         = post_author,
                        discovered_items    = ", ".join(discovery_list),
                        failed_items        = ", ".join(failure_list),
                        succeeded_items     = ", ".join(success_list),
                        skipped_items       = ", ".join(skipped_list),
                        # llm_prompt_tokens       = self.token_tracker.total_prompt_tokens,
                        # llm_completion_tokens   = self.token_tracker.total_completion_tokens,
                        llm_total_tokens        = self.token_tracker.total_tokens,
                        llm_call_count          = self.token_tracker.total_calls,
                    )
            
            except Exception as e:
                status = "error"
                print(f"Error during Translation: {e}")
                raise  # Re-raise to maintain original behavior

        missing_translations_stats.items_failed = missing_translations_stats.items_discovered - missing_translations_stats.items_succeeded
 
        return missing_translations_stats
    # ============================================================================
    # SINGLE FILE TRANSLATION IN ALL MISSING LANGUAGES
    # ============================================================================
    def translate_file(self, input_path: str, target_lang: str, domain:str) -> str:
        """
        Orchestrate translation of a single markdown file
        
        Args:
            input_path: Path to input markdown file
            target_lang: Target language code
            
        Returns:
            Path to output file
        """
        print(f"\n{'='*60}")
        print(f"🌍 Translating: {input_path} → {target_lang}")
        print(f"{'='*60}")
        
        # ============================================================================
        # Step 1: Parse markdown file
        # ============================================================================
        print("📄 Step 1: Parsing markdown file...")
        parsed = parse_markdown_file(input_path)
        frontmatter = parsed['frontmatter']
        content = parsed['content']
        print(f"   ✓ Parsed frontmatter with {len(frontmatter)} fields")
        print(f"   ✓ Content: {len(content)} characters")

        # ============================================================================
        # Step 2: Translate frontmatter using FrontmatterAgent
        # ============================================================================
        print(f"\n📋 Step 2: Translating frontmatter ({self.frontmatter_agent.name})...")
        translated_frontmatter = self.frontmatter_agent.translate(
            domain,
            frontmatter, 
            target_lang
        )
        print("   ✓ Frontmatter translated")
        
        # ============================================================================
        # Step 3: Translate content using ContentAgent
        # ============================================================================
        print(f"\n📝 Step 3: Translating content ({self.content_agent.name})...")
        translated_content = self.content_agent.translate(
            domain,
            content, 
            target_lang
        )
        # print(f"   ✓ Content translated:\n{translated_content}\n")
        
        # ============================================================================
        # Step 4: Perform any final adjustments if needed
        # ============================================================================
        # if translated_content contains currentDomain and does not contain /{target_lang}/, add it.
        # do this on all the occurrences.

        translated_content_adjusted = re.sub(
            rf"(https?://{re.escape(domain)}/)(?!{re.escape(target_lang)}/)", 
            rf"\1{target_lang}/",
            translated_content
        )
        # ============================================================================
        # if translated and adjusted is different, mean prompt missed some, so replace.
        # ============================================================================
        if translated_content != translated_content_adjusted:
            translated_content = translated_content_adjusted
            print(f"⚠️   ✓ Adjusted Content translated:\n{translated_content}\n")        
        # ============================================================================
        # Step 5: Write output file
        # ============================================================================
        print("\n💾 Step 4: Writing output file...")
        input_file = Path(input_path)
        output_path = input_file.parent / f"index.{target_lang}.md"
        
        result = write_markdown_file(
            str(output_path), 
            translated_frontmatter, 
            translated_content
        )
        print(f"   ✓ Saved to: {output_path}")
        
        print(f"\n{'='*60}")
        print(f"✅ Translation complete!")
        print(f"{'='*60}\n")
        
        return str(output_path)
    
# ============================================================================
# ARGUMENT PARSER BUILDING FUNCTION
# ============================================================================
def build_parser():
    parser = argparse.ArgumentParser(description="Translate Missing Translation Files")

    parser.add_argument(
        "--domain",
        type=str,
        required=True,
        help="Which DOMAIN to process (blog.aspose.com, blog.groupdocs.com, etc.) or ALL"
    )

    parser.add_argument(
        "--key",
        type=str,
        required=False,
        help="PROFESSIONALIZE LLM API KEY (REQUIRED)"
    )

    parser.add_argument(
        "--posts-list",
        type=json.loads,
        required=False,
        help="JSON string of posts list to translate (optional)",
    )

    parser.add_argument(
        "--product",
        type=str,
        required=False,
        help="Blog Post of which PRODUCT to process (optional)"
    )

    parser.add_argument(
        "--author",
        type=str,
        required=False,
        help="Blog Post of which AUTHOR to process (optional)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        required=False,
        help="LIMIT NUMBER OF POSTS to translate (optional)"
    )
    
    return parser

# ============================================================================
# ROW VALIDATION HELPER
# ============================================================================

def filter_valid_rows(posts_list: List[List[Any]]) -> List[List[Any]]:
    """
    Return only rows that contain the required fields for translation:
      col 0 — domain
      col 1 — product
      col 2 — slug
      col 6 — missing languages

    Filters out sentinel rows (e.g. '!!! NO MISSING TRANSLATION FOUND !!!'),
    blank rows, and any row with fewer than 7 columns.
    """
    if not posts_list:
        return posts_list
    return [
        row for row in posts_list
        if len(row) > 6
        and str(row[0]).strip()  # domain
        and str(row[1]).strip()  # product
        and str(row[2]).strip()  # slug
        and str(row[6]).strip()  # missing langs
    ]


# ============================================================================
# MAIN FUNCTION TO START TRANSLATION BASED ON ARGS
# ============================================================================

def start_translation(args=None, posts_list_to_translate: List[List[Any]]=None):
    print("⚠️  start_translation Called ⚠️")
    start_time = time.time()
    status = "success"
    try:
    
        parsed = None

        if args is not None:
            parser = build_parser()
            parsed = parser.parse_args(args)

        currentDomain = passed_domain = parsed.domain.strip().lower() if parsed else None
        
        key = (
            parsed.key.strip()
            if parsed and getattr(parsed, "key", None)
            else os.getenv("PROFESSIONALIZE_API_KEY")
        )

        if not key:
            raise RuntimeError(
                "API key not provided. Use --key or set PROFESSIONALIZE_API_KEY in environment variables."
            )

        target_product      = parsed.product.strip().lower() if parsed and parsed.product else None
        target_author       = parsed.author.strip().lower()  if parsed and parsed.author  else None
        translation_limit   = parsed.limit if parsed and parsed.limit is not None else config.domains_data[currentDomain][config.KEY_TRANSLATION_LIMIT]

        posts_list = posts_list_to_translate or (parsed.posts_list if parsed else None)

        print("Domain:", currentDomain)
        print("Product:", target_product)
        print("Author:", target_author)
        print("Limit:", translation_limit)

        if posts_list is None:
            print("Posts List Found NONE - READING FROM GOOGLE SHEET")
            
            if config.PRODUCTION_ENV:
                posts_list = read_from_google_spreadsheet(config.domains_data[currentDomain][config.KEY_SHEET_ID])
            else: #Test Environment
                posts_list = read_from_google_spreadsheet(config.SHEET_ID_TEST_QA)
                


        # Keep only rows that have the required fields: domain, product, slug, and missing langs
        if posts_list:
            posts_list = filter_valid_rows(posts_list)

        if not posts_list:
            print("="*60)
            print(f"No missing translations found for domain: {currentDomain} — nothing to do.")
            print("="*60)
            return

        # PRINTING POSTS LIST ==========================
        if posts_list is not None:
            print("="*60)
            for post in posts_list:
                print(post[1], " > ", post[2], " by ", post[3])
            print("="*60)

        # ======================
        # FILTER by AUTHOR
        # ======================
        if target_author is not None and posts_list is not None:
            posts_list = [row for row in posts_list if row[3].strip().lower() == target_author.strip().lower()]

        # ======================
        # FILTER by PRODUCT
        # ======================
        if target_product is not None and posts_list is not None:
            target_product = config.PRODUCT_MAP.get(target_product.strip().lower(), None)
            posts_list = [row for row in posts_list if row[1].strip().lower() == target_product.strip().lower()]

        # ======================
        # FILTER by LIMIT
        # ======================
        if translation_limit is not None and posts_list is not None:
            if translation_limit < len(posts_list):
                posts_list = posts_list[:translation_limit]

        if posts_list is None:
            print("="*60)
            print(f"There is nothing to translate....: {posts_list}")
            print("="*60)

        else:
            print(f"Starting Translation for {len(posts_list)} posts.")
            # PRINTING POSTS LIST ==========================
            print("="*60)
            for post in posts_list:
                print(post[1], " > ", post[2], "\tby\t>\t", post[4])
            print("="*60)


            orchestrator = TranslationOrchestrator(api_key=key)
            metrics = orchestrator.translate_files(currentDomain, target_author, translation_limit, posts_list)

    except Exception as e:
        status = "error"
        print(f"Error during execution: {e}")
        raise  # Re-raise to maintain original behavior

    end_time = time.time()
    run_duration_ms = int((end_time - start_time) * 1000)
    run_id = str(uuid.uuid4())

    product_full_name = config.PRODUCT_MAP[currentDomain][target_product] if target_product else config.JOB_ALL_PRODUCTS

    metrics_product = currentDomain
    if target_product:
        metrics_product = config.PRODUCT_MAP[currentDomain][target_product] if target_product else config.JOB_ALL_PRODUCTS

    # send_metrics(    run_id, 
    #                         status, 
    #                         run_duration_ms, 
    #                         agent_name=config.AGENT_BLOG_POST_TRANSLATOR, 
    #                         job_type= config.JOB_TYPE_TRANSLATION,
    #                         item_name=config.JOB_ITEM_TRANSLATIONS,
    #                         items_discovered=metrics.items_discovered,
    #                         items_failed=metrics.items_failed,
    #                         items_succeeded=metrics.items_succeeded,
    #                         product=metrics_product #product_full_name
    #                     )


# Example usage
if __name__ == "__main__":
    print("⚠️  Main Called ⚠️")
    start_translation(sys.argv[1:])

