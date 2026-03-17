import requests
import time
import uuid
from datetime import datetime, timedelta, timezone
import config

def send_metrics(   run_id,
                    status,
                    run_duration_ms,
                    agent_name,
                    job_type,
                    item_name,
                    items_discovered,
                    items_failed,
                    items_succeeded,
                    items_skipped,
                    website,
                    website_section         = config.WEBSITE_SECTION_BLOG,
                    agent_owner             = config.AGENT_OWNER,
                    product                 = config.JOB_ALL_PRODUCTS,
                    platform                = config.JOB_ALL_PLATFORMS,
                    post_dir                = "",
                    post_url                = "",
                    post_author             = "",
                    discovered_items        = "",
                    failed_items            = "",
                    succeeded_items         = "",
                    skipped_items           = "",
                    llm_total_tokens        = 0,
                    llm_call_count          = 0,
                 ):
    payload = {
        "timestamp"             : datetime.now(timezone(timedelta(hours=5))).isoformat(),
        "agent_name"            : agent_name,
        "agent_owner"           : agent_owner,
        "job_type"              : job_type,
        "run_id"                : run_id,
        "status"                : status,
        "product"               : product,
        "platform"              : platform,
        "website"               : website,
        "website_section"       : website_section,
        "item_name"             : item_name,
        "items_discovered"      : items_discovered,
        "items_failed"          : items_failed,
        "items_succeeded"       : items_succeeded,
        "items_skipped"         : items_skipped,
        "run_duration_ms"       : run_duration_ms,
        "post_dir"              : post_dir,
        "post_url"              : post_url,
        "post_author"           : post_author,
        "discovered_items"      : discovered_items,
        "failed_items"          : failed_items,
        "succeeded_items"       : succeeded_items,
        "skipped_items"         : skipped_items,
        "token_usage"           : llm_total_tokens,
        "api_calls_count"       : llm_call_count,
    }
    print(f"PAYLOAD:\n{payload}")
    
    # Send metrics when in PRODUCTION and Agent is not the BLOG SCANNER (to avoid skewing translation metrics with scans)
    if config.PRODUCTION_ENV and agent_name != config.AGENT_BLOG_SCANNER:
        try:
            response = requests.post(f"{config.METRICS_URL}?token={config.METRICS_TOKEN}", json=payload, headers={"Content-Type": "application/json"})
            if response.status_code == 200:
                print("✅ Metrics sent successfully")
            else:
                print(f"Failed to send metrics: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Error sending metrics: {e}")

    try:
        payload["run_env"] = "PROD" if config.PRODUCTION_ENV else "DEV"
        print(f"PAYLOAD:\n{payload}")

        response = requests.post(f"{config.METRICS_URL_DEV}?token={config.METRICS_TOKEN_DEV}", json=payload, headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            print("✅ Metrics sent successfully")
        else:
            print(f"Failed to send metrics: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error sending metrics: {e}")