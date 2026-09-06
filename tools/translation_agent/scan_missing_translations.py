import os
import re
import openpyxl
import gspread
import argparse
import config
import time
import uuid
import random

from utils import send_metrics
from config import Stats

from google.oauth2.service_account import Credentials
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment
from datetime import datetime
from git import Repo
from git_repo_utils import clone_or_pull_repos
from io_google_spreadsheet import write_to_google_spreadsheet, write_domain_scan_results, update_history_tab
from translation_files_managers import delete_translation_files
from translator import start_translation

# =====================================================================
# Parse command-line arguments
# =====================================================================
parser = argparse.ArgumentParser(description="Detect Missing Translations")

parser.add_argument(
    "--key",
    type=str,
    required=False,
    help="PROFESSIONALIZE LLM API KEY (REQUIRED)"
)

parser.add_argument(
    "--domain",
    type=str,
    required=True,
    help="Which domain to process (blog.aspose.com, blog.groupdocs.com, etc.) or ALL"
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
parser.add_argument(
    "--translate",
    type=bool,
    required=False,
    help="Do you also want to translate or just scan? (optional)"
)

args = parser.parse_args()
passed_domain = args.domain.strip().lower()

# key                 = args.key.strip() if args and args.key else None
key = (
    args.key.strip()
    if args and getattr(args, "key", None)
    else os.getenv("PROFESSIONALIZE_API_KEY")
)

target_product      = args.product.strip() if args and args.product else None
target_author       = args.author.strip().lower()  if args and args.author  else None
translation_limit   = args.limit if args and args.limit is not None else None
is_translate        = args.translate if args and args.translate is not None else False

# ===============================================
# APP support following DOMAINS

all_domains = {
    config.DOMAIN_ASPOSE_COM,
    config.DOMAIN_GROUPDOCS_COM,
    config.DOMAIN_CONHOLDATE_COM,
    config.DOMAIN_ASPOSE_CLOUD,
    config.DOMAIN_GROUPDOCS_CLOUD,
    config.DOMAIN_CONHOLDATE_CLOUD,
}
selected_domains = []

if passed_domain == "all":
    selected_domains = list(all_domains)

elif passed_domain in all_domains:
    selected_domains = [passed_domain]

else:
    print(f"[ERROR] Invalid domain: {passed_domain}")
    print("Valid options:")
    for d in all_domains:
        print(" --domain ", d)
    exit(1)

print("Processing domains: ", selected_domains)

SUMMARY_DATA = []

# -------------------------
# 4. MAIN APPLICATION LOGIC
# -------------------------

def main():
    start_time = time.time()
    status = "success"
    try:
        # clone_or_pull_repos()
        metrics = validate_existing_translation_files(selected_domains)
        # delete_extra_translations()
    except Exception as e:
        status = "error"
        print(f"Error during execution: {e}")
        raise  # Re-raise to maintain original behavior

    end_time = time.time()
    run_duration_ms = int((end_time - start_time) * 1000)
    run_id = str(uuid.uuid4())

    current_domain = selected_domains[0] if len(selected_domains) == 1 else ""
    root_domain = current_domain.replace("blog.", "")

    product_full_name = config.PRODUCT_MAP[current_domain][target_product] if target_product else config.PRODUCT_MAP[current_domain]["total"]


    send_metrics(    run_id, 
                            status, 
                            run_duration_ms, 
                            agent_name          = config.AGENT_BLOG_SCANNER, 
                            job_type            = config.JOB_TYPE_SCANNING,
                            item_name           = config.JOB_ITEM_MISS_TRANSLATIONS,
                            items_discovered    = metrics.items_discovered,
                            items_failed        = metrics.items_failed,
                            items_succeeded     = metrics.items_succeeded,
                            items_skipped       = 0,
                            website             = root_domain,
                            product             = product_full_name,
                            platform            = config.JOB_ALL_PLATFORMS  
                        )

    print("\n========= END =========")

# ===============================================
# re.compile(r"^index(\.(ar|cs|de|es|fa|fr|he|id|it|ja|ko|nl|pl|pt|ru|th|tr|uk|vi|zh-hant|zh))?\.md$")
def validate_existing_translation_files(domains): #path_to_valid_extensions
    """
    Validates multiple paths using their respective valid markdown file extensions.

    Args:
        path_to_valid_extensions (dict): A dictionary mapping paths to their valid file extensions.
    """
    missing_translations_stats = Stats(0, 0, 0, 0)
    current_date = datetime.now().strftime("%Y-%m-%d")
    scan_date    = datetime.now().astimezone().isoformat()

    global target_product
    print("=================================================================")
    print("\t\tMissing OR Invalid Translations")
    print("=================================================================")
    
    #for path, valid_extensions in path_to_valid_extensions.items():
    for domain in domains:
        local_repo_path = config.domains_data[domain][config.KEY_LOCAL_GITHUB_REPO]
        valid_extensions = config.domains_data[domain][config.KEY_SUPPORTED_LANGS]
        sheet_id = config.domains_data[domain][config.KEY_SHEET_ID]

        # print(f"{domain} ->\n\tSheet ID: {sheet_id}\n\tSupported Langs: {valid_extensions}\n\tRepo: {local_repo_path}\n")

        if os.path.exists(local_repo_path):
            # valid_md_file_regex = re.compile(r"^index(\.(" + valid_extensions + "))?\.md$")
            valid_md_file_regex = re.compile(r"^index(?:\.(" + valid_extensions + r"))?\.md$")
            total_valid_files_count = len(valid_extensions.split("|")) + 1  # Include "index.md"

            # print (f"valid_md_file_regex: {valid_md_file_regex}")
            # print (f"total_valid_files_count: {total_valid_files_count}")

            result = validate_blog_dirs(local_repo_path, valid_md_file_regex, valid_extensions, total_valid_files_count)
            # print (f"Invalid Translations Investigation Result ->\n{result}")

            # print(f"{domain_name}     \t-\t {len(result)}\tInvalid blog directories. ")
            print(f"{domain}  \t-   {len(result)}\t-  Invalid Blog DIRs.  >  ", end=' ', flush=True)
            # print_on_console(result)
            # print(f"- {domain_name}\t- @github.com/{username}/{repo_name}.git ...  \t - Pulling latest ...  ", end=' ', flush=True)

            # =============== SAVE ==============

            # for name in input_names:
            #     # Convert the input name to title case to match the dictionary keys
            #     formatted_name = name.title()
            #     if formatted_name in DEV:
            #         handles_list.append(DEV[formatted_name])

            # Join the found handles into a single string
            
            handles_list = config.domains_data[domain][config.KEY_MENTIONS_AUTHOR]

            converted_result = []
            if result:
                for item in result:
                    base_fields = [
                        domain,
                        item[config.KEY_PRODUCT_NAME],
                        item[config.KEY_DIR_BASE],
                        (f"{domain}{item[config.KEY_POST_URL]}"),
                        item[config.KEY_AUTHOR],
                    ]

                    if item[config.KEY_MISSING_COUNT] > 0:
                        converted_result.append(base_fields + [
                            config.ISSUE_MISSING,
                            item[config.KEY_MISSING_COUNT],
                            ", ".join(item[config.KEY_MISSING_FILES]),  # Convert list to string
                            config.ACTION_TRANSLATE,
                            "",  # Status column, can be filled manually later
                        ])

                    if item[config.KEY_EXTRA_COUNT] > 0:
                        converted_result.append(base_fields + [
                            config.ISSUE_EXTRA,
                            item[config.KEY_EXTRA_COUNT],
                            ", ".join(item[config.KEY_EXTRA_FILES]),  # Convert list to string
                            config.ACTION_DELETE,
                            "",  # Status column, can be filled manually later
                        ])

                    person = item[config.KEY_AUTHOR].strip().lower()
                    official_handle = config.DEV_NORMALIZED.get(person)  # safely get the handle
                    # print(f"handle: {official_handle}")

                    missing_translations_stats.items_discovered += item[config.KEY_MISSING_COUNT]

                    if official_handle:
                        if official_handle not in handles_list:
                            handles_list.append(official_handle)
                            # print(f"added: {official_handle}")
                    else:
                        print(f"\n⚠️ Handle not found for: {person}")

                # --- Sorting Logic ---
                # Sorts the list 'converted_result' in-place based on the element at index 2 (column C/3)
                converted_result.sort(key=lambda x: x[2])

            else:
                converted_result.append(["", "!!! NO MISSING TRANSLATION FOUND !!!"])

            # --- Write to consolidated scan sheet ---
            write_domain_scan_results(
                domain    = domain,
                scan_date = scan_date,
                rows      = converted_result if result else [],
                headers   = config.HEADERS_MISSING_TRANSLATIONS
            )
            update_history_tab(
                domain       = domain,
                scan_date    = scan_date,
                current_rows = converted_result if result else [],
            )

            max_retries = 3
            # generate random delay between 2 to 5 seconds
            retry_delay = random.randint(2, 6)

            sheet_link = None

            for attempt in range(max_retries):
                if config.PRODUCTION_ENV:
                    sheet_link = write_to_google_spreadsheet(sheet_id, valid_extensions, config.HEADERS_MISSING_TRANSLATIONS, converted_result)
                else:
                    sheet_link = write_to_google_spreadsheet(config.SHEET_ID_TEST_QA, valid_extensions, config.HEADERS_MISSING_TRANSLATIONS, converted_result, f"{domain}-{current_date}")

                if sheet_link:
                    print(f"✅ Scan results written to sheet.")
                    break  # Success! Exit loop
                else:
                    print(f"Attempt {attempt + 1} failed. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)

            if sheet_link:
                missing_translations_stats.items_succeeded = missing_translations_stats.items_discovered
            else:
                print("Failed to write to spreadsheet after multiple attempts.")
                missing_translations_stats.items_failed = missing_translations_stats.items_discovered


            handles_string = " ".join(handles_list)
            print(f"handles_string: {handles_string}\n")

            domains_missing_file_info = [current_date, domain, len(result), handles_string, sheet_link, config.SEND_EMAIL_TRUE if result else config.SEND_EMAIL_FALSE]
            SUMMARY_DATA.append(domains_missing_file_info)
            # print(f"Summary > {domains_missing_file_info}")
            # =============== SAVE ==============
            # print(f"Validation results saved to:\n{output_file_name}")

            # ========================================
            # Translate Missing Files
            # ========================================

            # print(f"Blog Post List:\n{converted_result}")
            
            # print("Domain:", domain)
            # print("Product:", target_product)
            # print("Author:", target_author)
            # print("Limit:", translation_limit)
            # print("Key:", "********" if key else "NO KEY")

            args = ["--domain", domain]

            if target_product:
                target_product = config.PRODUCT_MAP.get(target_product.strip().lower(), None)
                args += ["--product", target_product]

            if target_author:
                args += ["--author", target_author]

            if translation_limit:
                args += ["--limit", str(translation_limit)]

            if key:
                args += ["--key", key]
            else:
                print("⚠️  No PROFESSIONALIZE KEY AVAILABLE ⚠️")
                print("⚠️  KEY IS REQUIRED FOR TRANSLATION ⚠️")
                break

            safe_args = ["***" if (i > 0 and args[i-1] == "--key") else a for i, a in enumerate(args)]
            print(f"args: {safe_args}")
            
            if is_translate:
                print(f"Translating Missing Files for: {domain}...")
                print("✅ == AUTO TRANSLATION TEMPORARILY PAUSED == ✅")
                # start_translation(args, posts_list_to_translate=converted_result)
            else:
                print("✅ == Scanning COMPLETED == ✅")
                print("❌ == AUTO TRANSLATION NOT REQUESTED == ❌")

        else:
            print(f"The path '{local_repo_path}' does not exist.")


    print("=================================================================")

    if config.PRODUCTION_ENV:
        sheet_link = write_to_google_spreadsheet(config.SHEET_ID_SUMMARY, None , config.HEADERS_SUMMARY, SUMMARY_DATA)
    else:
        sheet_link = write_to_google_spreadsheet(config.SHEET_ID_TEST_QA, None ,config.HEADERS_SUMMARY, SUMMARY_DATA, f"SUM-{current_date}")

    print(f"✅ Summary written to sheet.")

    return missing_translations_stats

# =========================================
def validate_blog_dirs(base_path, valid_md_file_regex, valid_extensions, total_valid_files_count):
    """
    Validates blog directories for missing markdown files and extracts the author name from index.md.

    Args:
        base_path (str): The root path containing the blog directories.
        valid_md_file_regex (re.Pattern): Compiled regex pattern for valid markdown file names.
        total_valid_files_count (int): Total count of valid markdown files.

    Returns:
        list: A list of dictionaries containing blog directory details with missing file information and author name.
    """
    invalid_blog_dirs = []
    # author_regex = re.compile(r'author:\s*"?([^"]+)"?')  # Matches author: "Name" or author: Name
    author_regex    = re.compile(r"author:\s*['\"]?([^'\"]+)['\"]?")
    url_regex       = re.compile(r"url:\s*['\"]?([^\s'\"]+)['\"]?")
    draft_regex     = re.compile(r"^draft:\s*['\"]?true['\"]?\s*$", re.IGNORECASE)

    for product_name in os.listdir(base_path):
        product_path = os.path.join(base_path, product_name)
        if os.path.isdir(product_path):
            for blog_dir in os.listdir(product_path):
                if blog_dir.startswith(("2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027")) and "discount" not in blog_dir:
                    blog_dir_path = os.path.join(product_path, blog_dir)
                    if os.path.isdir(blog_dir_path):
                        md_files = {file for file in os.listdir(blog_dir_path) if file.endswith(".md")}
                        valid_files = {file for file in md_files if valid_md_file_regex.match(file)}

                        missing_count = total_valid_files_count - len(valid_files)
                        missing_files = sorted(
                            f"{lang}" if lang != "md" else "index.md"
                            for lang in valid_extensions.split("|")
                            if f"index.{lang}.md" not in valid_files and lang != "md" or "index.md" not in valid_files
                        )
                        
                        excessive_files = md_files - valid_files

                        # if (excessive_files):
                        #     print("DIR: " + blog_dir_path)
                        #     print(f"excessive_files:\n{excessive_files}")
                        # else:
                        #     print("== NO EXTRA TRANSLATIONS == ")

                        excessive_ext = [file_name.split('.')[1] for file_name in excessive_files]


                        # Extract author from index.md
                        author_name = None
                        url_link = None
                        is_draft = False

                        index_md_path = os.path.join(blog_dir_path, "index.md")

                        # print(f"index_md_path: {index_md_path}")

                        if os.path.exists(index_md_path):
                            # print(f"path exists...")
                            try:
                                with open(index_md_path, "r", encoding="utf-8") as f:
                                    for line in f:
                                        # Search for draft flag if we haven't found it yet
                                        if not is_draft and draft_regex.match(line.strip()):
                                            is_draft = True

                                        # Search for author if we haven't found it yet
                                        if not author_name:
                                            author_match = author_regex.search(line)
                                            if author_match:
                                                author_name = author_match.group(1).strip()

                                        # Search for url if we haven't found it yet
                                        if not url_link:
                                            url_match = url_regex.search(line)
                                            if url_match:
                                                url_link = url_match.group(1).strip()

                                        # Break ONLY when both have been found
                                        if author_name and url_link:
                                            break

                            except UnicodeDecodeError as e:
                                print(f"❌❌ UnicodeDecodeError while reading: {index_md_path} ❌❌")
                                print(f"   → {e}")

                        # Skip draft posts entirely — draft: true means the source content
                        # isn't final yet and it won't be reflected in translations once set.
                        if is_draft:
                            continue

                        if missing_count > 0 or excessive_files:
                            invalid_blog_dirs.append({
                                config.KEY_PRODUCT_NAME    : product_name,
                                config.KEY_DIR_BASE        : blog_dir,
                                config.KEY_POST_URL        : url_link,
                                config.KEY_AUTHOR          : author_name.strip(),  # Add extracted author name
                                config.KEY_MISSING_COUNT   : missing_count,
                                config.KEY_MISSING_FILES   : missing_files,
                                config.KEY_EXTRA_FILES     : sorted(excessive_ext) if len(excessive_ext) > 0 else "-",
                                config.KEY_EXTRA_COUNT     : len(excessive_ext)
                            })
    return invalid_blog_dirs

# =========================================
def print_on_console(output):
    print(f"Invalid blog directories : {len(output)} ")
    
# =========================================
def delete_extra_translations():

    # delete_translation_files(LOC_GIT_REPO_ASPOSE_COM        , LANGS_ASPOSE_COM)
    # delete_translation_files(LOC_GIT_REPO_GROUPDOCS_COM     , LANGS_GROUPDOCS_COM)
    # delete_translation_files(LOC_GIT_REPO_CONHOLDATE_COM    , LANGS_CONHOLDATE_COM)
    # delete_translation_files(LOC_GIT_REPO_ASPOSE_CLOUD      , LANGS_ASPOSE_CLOUD)
    # delete_translation_files(LOC_GIT_REPO_GROUPDOCS_CLOUD   , LANGS_GROUPDOCS_CLOUD)
    # delete_translation_files(LOC_GIT_REPO_CONHOLDATE_CLOUD   , LANGS_CONHOLDATE_CLOUD)
    print("==== EXTRA TRANSLATIONS DELETED ====")

# =========================================
# 5. ENTRY POINT
if __name__ == "__main__":
    main()