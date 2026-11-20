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
from io_google_spreadsheet import write_to_google_spreadsheet, sync_domain_queue, replace_cleanup_rows
from translation_files_managers import delete_translation_files
from translator import start_translation
from scan_queue import post_date, ready_after
from scan_helpers import (read_post_meta, git_history, outdated_langs,
                          missing_note, extra_note, outdated_note, waiting_note)

# Result keys used only inside this scanner
KEY_OUTDATED_FILES      = "outdated_files"
KEY_SOURCE_COMMIT_TIME  = "source_commit_time"
KEY_ROW_NOTES           = "row_notes"       # {issue: Notes text}

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

        # print(f"{domain} ->\n\tSheet ID: {sheet_id}\n\tSupported Langs: {valid_extensions}\n\tRepo: {local_repo_path}\n")

        if os.path.exists(local_repo_path):
            # valid_md_file_regex = re.compile(r"^index(\.(" + valid_extensions + "))?\.md$")
            valid_md_file_regex = re.compile(r"^index(?:\.(" + valid_extensions + r"))?\.md$")
            total_valid_files_count = len(valid_extensions.split("|")) + 1  # Include "index.md"

            # print (f"valid_md_file_regex: {valid_md_file_regex}")
            # print (f"total_valid_files_count: {total_valid_files_count}")

            all_posts = set()     # every (product, post folder) seen — validates manual queue rows
            result = validate_blog_dirs(local_repo_path, valid_md_file_regex, valid_extensions, total_valid_files_count,
                                        all_posts=all_posts)
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

            findings         = []     # MISSING / OUTDATED, one dict per (post, issue) — reconciled into the queue
            outdated_rows    = []     # (index.md commit time, finding) — sorted newest post first below
            extra_rows       = []     # EXTRA → the cleanup tab
            missing_or_extra = 0      # posts with a MISSING/EXTRA issue (summary count)
            for item in result:
                base = {
                    config.KEY_DOMAIN       : domain,
                    config.KEY_PRODUCT_NAME : item[config.KEY_PRODUCT_NAME],
                    config.KEY_DIR_BASE     : item[config.KEY_DIR_BASE],
                    config.KEY_POST_URL     : f"{domain}{item[config.KEY_POST_URL]}",
                    config.KEY_AUTHOR       : item[config.KEY_AUTHOR],
                }

                def finding(issue, langs):
                    return {**base,
                            config.KEY_ISSUE         : issue,
                            config.KEY_MISSING_COUNT : str(len(langs)),
                            config.KEY_MISSING_FILES : ", ".join(langs),
                            config.KEY_ACTION        : config.ISSUE_ACTIONS[issue],
                            config.KEY_NOTES         : item[KEY_ROW_NOTES].get(issue, ""),
                            # settling time: Step 2 waits until then (new and edited posts alike)
                            config.KEY_READY_AFTER   : ready_after(item[KEY_SOURCE_COMMIT_TIME])}

                if item[config.KEY_MISSING_COUNT] > 0:
                    findings.append(finding(config.ISSUE_MISSING, item[config.KEY_MISSING_FILES]))
                if item[config.KEY_EXTRA_COUNT] > 0:
                    extra_rows.append(finding(config.ISSUE_EXTRA, item[config.KEY_EXTRA_FILES]))
                if item[KEY_OUTDATED_FILES]:
                    outdated_rows.append((item[KEY_SOURCE_COMMIT_TIME],
                                          finding(config.ISSUE_OUTDATED, item[KEY_OUTDATED_FILES])))

                missing_translations_stats.items_discovered += item[config.KEY_MISSING_COUNT]

                # Authors are mentioned for missing/extra translations only —
                # an outdated translation (English edited later) isn't theirs to fix
                if not (item[config.KEY_MISSING_COUNT] or item[config.KEY_EXTRA_COUNT]):
                    continue
                missing_or_extra += 1

                person = item[config.KEY_AUTHOR].strip().lower()
                official_handle = config.DEV_NORMALIZED.get(person) if person else None

                if official_handle:
                    if official_handle not in handles_list:
                        handles_list.append(official_handle)
                else:
                    print(f"\n⚠️ Handle not found for: {person or '(no author in index.md)'}")

            # New queue rows are added in this order: MISSING by post folder, then
            # OUTDATED newest post first (folder date; same date → most recently
            # edited English first). Existing rows keep their place; Step 2 orders
            # by Priority, then sheet order (first in, first out), OUTDATED newest post first.
            findings.sort(key=lambda f: f[config.KEY_DIR_BASE])
            outdated_rows.sort(key=lambda t: (-post_date(t[1][config.KEY_DIR_BASE]), -t[0],
                                              t[1][config.KEY_DIR_BASE]))
            findings += [f for _, f in outdated_rows]
            extra_rows.sort(key=lambda f: f[config.KEY_DIR_BASE])
            print(f"{len(outdated_rows)} outdated  >  ", end=' ', flush=True)

            # --- Reconcile the queue (domain tab); closed rows move to history ---
            synced = sync_domain_queue(domain, findings, scan_date, posts=all_posts,
                                       supported_langs=[l for l in valid_extensions.split("|") if l])
            replace_cleanup_rows(domain, extra_rows, scan_date)
            sheet_link = synced["url"]

            if synced["ok"]:
                missing_translations_stats.items_succeeded = missing_translations_stats.items_discovered
            else:
                print("❌ Queue not updated — see the error above.")
                missing_translations_stats.items_failed = missing_translations_stats.items_discovered


            handles_string = " ".join(handles_list)
            print(f"handles_string: {handles_string}\n")

            domains_missing_file_info = [current_date, domain, missing_or_extra, handles_string, sheet_link, config.SEND_EMAIL_TRUE if missing_or_extra else config.SEND_EMAIL_FALSE]
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

            if is_translate and not key:
                # Scanning needs no LLM key; only --translate does
                print("⚠️  --translate needs PROFESSIONALIZE_API_KEY — skipping translation ⚠️")
            elif is_translate:
                args += ["--key", key]
                safe_args = ["***" if (i > 0 and args[i-1] == "--key") else a for i, a in enumerate(args)]
                print(f"args: {safe_args}")
                print(f"Translating Missing Files for: {domain}...")
                print("✅ == AUTO TRANSLATION TEMPORARILY PAUSED == ✅")
                # start_translation(args)   # Step 2 reads the queue (domain tab) itself
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
def validate_blog_dirs(base_path, valid_md_file_regex, valid_extensions, total_valid_files_count,
                       all_posts: set = None):
    """
    Find posts with missing, extra or outdated translations.

    Skipped: folders without index.md (nothing to translate from), draft posts,
    non-dated folders and discount posts. A translation is outdated when its
    post's index.md was committed after it (git history of base_path; skipped
    when base_path isn't a git checkout, e.g. the local test mirror).

    Returns a list of dicts, one per post with at least one issue. If all_posts
    is given, every post checked (non-draft, with index.md) is added to it as
    (product, post folder) — used to validate manual queue rows.
    """
    invalid_blog_dirs = []
    supported_langs = [l for l in valid_extensions.split("|") if l]

    commits, files_by_sha = git_history(base_path)
    commit_times = {path: c.time for path, c in commits.items()} if commits else None
    if commit_times is None:
        print(f"\n⚠️  No git history for {base_path} — OUTDATED check skipped.")

    for product_name in os.listdir(base_path):
        product_path = os.path.join(base_path, product_name)
        if not os.path.isdir(product_path):
            continue
        for blog_dir in os.listdir(product_path):
            if not blog_dir.startswith(("2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027")) or "discount" in blog_dir:
                continue
            blog_dir_path = os.path.join(product_path, blog_dir)
            index_md_path = os.path.join(blog_dir_path, "index.md")
            # No English source: nothing can be translated from this folder
            if not os.path.isdir(blog_dir_path) or not os.path.exists(index_md_path):
                continue

            try:
                meta = read_post_meta(index_md_path)
            except (OSError, UnicodeDecodeError) as e:
                print(f"❌❌ Could not read: {index_md_path} → {e}")
                continue

            # Skip draft posts entirely — draft: true means the source content
            # isn't final yet and it won't be reflected in translations once set.
            if meta["draft"]:
                continue
            if all_posts is not None:
                all_posts.add((product_name, blog_dir))

            md_files    = {file for file in os.listdir(blog_dir_path) if file.endswith(".md")}
            valid_files = {file for file in md_files if valid_md_file_regex.match(file)}

            missing_files = sorted(l for l in supported_langs if f"index.{l}.md" not in valid_files)
            present_langs = [l for l in supported_langs if f"index.{l}.md" in valid_files]
            excessive_ext = sorted(file_name.split('.')[1] for file_name in md_files - valid_files)
            outdated      = (outdated_langs(commit_times, f"{product_name}/{blog_dir}", present_langs)
                             if commit_times else [])

            if missing_files or excessive_ext or outdated:
                post_rel_dir = f"{product_name}/{blog_dir}"
                en_time = commit_times.get(f"{post_rel_dir}/index.md", 0) if commit_times else 0
                notes = {}
                if missing_files:
                    notes[config.ISSUE_MISSING] = missing_note(len(missing_files), len(supported_langs))
                if excessive_ext:
                    notes[config.ISSUE_EXTRA] = extra_note()
                if outdated:
                    notes[config.ISSUE_OUTDATED] = outdated_note(commits, post_rel_dir, outdated,
                                                                 files_by_sha=files_by_sha,
                                                                 present_langs=present_langs)
                # English edited too recently: say so on the rows Step 2 will hold back
                wait = waiting_note(en_time, config.TRANSLATION_SETTLE_HOURS, int(time.time()))
                if wait:
                    for issue in (config.ISSUE_MISSING, config.ISSUE_OUTDATED):
                        if issue in notes:
                            notes[issue] = f"{notes[issue]}\n{wait}" if notes[issue] else wait
                invalid_blog_dirs.append({
                    config.KEY_PRODUCT_NAME    : product_name,
                    config.KEY_DIR_BASE        : blog_dir,
                    config.KEY_POST_URL        : meta["url"],
                    config.KEY_AUTHOR          : meta["author"],
                    config.KEY_MISSING_COUNT   : len(missing_files),
                    config.KEY_MISSING_FILES   : missing_files,
                    config.KEY_EXTRA_FILES     : excessive_ext if excessive_ext else "-",
                    config.KEY_EXTRA_COUNT     : len(excessive_ext),
                    KEY_OUTDATED_FILES         : outdated,
                    KEY_SOURCE_COMMIT_TIME     : en_time,
                    KEY_ROW_NOTES              : notes,
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