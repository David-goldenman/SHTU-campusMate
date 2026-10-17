"""Provider metadata exported from the project's pinned official Harness runtime."""
import json
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name('catalog.json').read_text(encoding='utf-8'))
PROVIDERS = {item['id']: item for item in CATALOG['providers']}
PROTOCOLS = ('openai-completions', 'openai-responses', 'anthropic-messages')


def runtime_route(config):
    """Use Harness's native adapter; credentials stay in the child environment."""
    if config['provider'] == 'deepseek':
        return 'deepseek-official', []
    profile = {}
    if config['key_saved']:
        profile['apiKeyEnv'] = 'CAMPUS_AI_API_KEY'
    if config.get('base_url'):
        profile['baseURL'] = config['base_url']
    if config['custom']:
        profile.update(api=config['protocol'], models=[{'id': config['model']}])
        if config.get('image_input'):
            profile['models'][0]['input'] = ['text', 'image']
    return config['provider'], [{'insert': [{'id': 'campus-provider', 'name': '@deepseek-ai/dsh-llm-pi-ai',
                                           'config': {'providers': {config['provider']: profile}}}]}]
