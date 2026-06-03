from git import Repo
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import config

def clone_or_pull_repos():
    token = config.PAT_GITHUB_SK

    # List of repositories with custom clone paths
    repos = [
        {
            "username": "aspose",
            "repo_name": "aspose-blog",
            "domain_name": "blog.aspose.com",
            "clone_path": config.CLONE_PATH_GITHUB_ASPOSE_COM
        },
        {
            "username": "groupdocs",
            "repo_name": "groupdocs-blog",
            "domain_name": "blog.groupdocs.com",
            "clone_path": config.CLONE_PATH_GITHUB_GROUPDOCS_COM
        },
        {
            "username": "conholdate",
            "repo_name": "conholdate-blog",
            "domain_name": "blog.conholdate.com",
            "clone_path": config.CLONE_PATH_GITHUB_CONHOLDATE_COM
        },
        {
            "username": "aspose-cloud",
            "repo_name": "aspose-cloud-blog",
            "domain_name": "blog.aspose.cloud",
            "clone_path": config.CLONE_PATH_GITHUB_ASPOSE_CLOUD
        },
        {
            "username": "groupdocs-cloud",
            "repo_name": "groupdocs-cloud-blog",
            "domain_name": "blog.groupdocs.cloud",
            "clone_path": config.CLONE_PATH_GITHUB_GROUPDOCS_CLOUD
        },
        {
            "username": "conholdate-cloud",
            "repo_name": "blog.conholdate.cloud",
            "domain_name": "blog.conholdate.cloud",
            "clone_path": config.CLONE_PATH_GITHUB_CONHOLDATE_CLOUD
        },
    ]
    
    print("=================================================================")
    print("\t\tCloning and Pulling Latest ...")
    print("=================================================================")

    for repo_info in repos:
        username = repo_info["username"]
        repo_name = repo_info["repo_name"]
        domain_name = repo_info["domain_name"]
        clone_path = f"{repo_info['clone_path']}/{repo_name}" 
        
        repo_url = f"https://{token}@github.com/{username}/{repo_name}.git"

        if not os.path.exists(clone_path):
            print(f"Cloning {repo_name} into {clone_path}...")
            Repo.clone_from(repo_url, clone_path)
            
        else:
            # print(f"- {domain_name}\t - @github.com/{username}/{repo_name}.git ...  \t - Pulling latest ...  ", end=' ', flush=True)
            print(f"- {domain_name}\t ... \t > Pulling latest ...  ", end=' ', flush=True)
            repo = Repo(clone_path)
            origin = repo.remotes.origin
            origin.pull()

        print("Done.\n")
