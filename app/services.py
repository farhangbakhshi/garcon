class Services:
    def process_webhook(self, repository_payload):
        repo_name = repository_payload.get('repository', {}).get('name')
        repo_url = repository_payload.get('repository', {}).get('html_url')
        return {'repo_name': repo_name, 'repo_url': repo_url}