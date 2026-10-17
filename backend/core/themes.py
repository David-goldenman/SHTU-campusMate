from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field


class Theme(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,47}$')
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=500)
    api_version: int = Field(default=1, ge=1, le=1)
    styles: list[str] = Field(default_factory=list, max_length=12)
    preview: str | None = None
    entry: str | None = None
    views: dict[str, str] = Field(default_factory=dict, max_length=100)
    backgrounds: dict[str, str] = Field(default_factory=dict, max_length=100)


def catalog(root: Path):
    items, errors = [], []
    root = root.resolve()
    for path in sorted(root.glob('*/theme.json')):
        try:
            if not path.resolve().is_relative_to(root):
                raise ValueError('主题清单须位于 themes 目录。')
            value = Theme.model_validate_json(path.read_text(encoding='utf-8'))
            if value.id != path.parent.name:
                raise ValueError('主题 ID 须与目录名称一致。')
            def asset(relative, extensions):
                target = (path.parent / relative).resolve()
                if not target.is_relative_to(root) or target.suffix not in extensions or not target.is_file():
                    raise ValueError('资源须为 themes 目录中的有效本地文件。')
                return '/assets/themes/' + quote(target.relative_to(root).as_posix())
            item = value.model_dump()
            item['styles'] = [asset(name, {'.css'}) for name in value.styles]
            item['preview'] = asset(value.preview, {'.svg', '.png', '.webp', '.jpg'}) if value.preview else None
            item['entry'] = asset(value.entry, {'.js', '.mjs'}) if value.entry else None
            for field in ('views', 'backgrounds'):
                item[field] = {key: asset(name, {'.js', '.mjs'}) for key, name in getattr(value, field).items()}
            items.append(item)
        except (OSError, ValueError):
            errors.append({'id': path.parent.name, 'message': '主题清单或资源无效，请检查 theme.json。'})
    return {'api_version': 1, 'default': 'default', 'items': sorted(items, key=lambda item: (item['id'] != 'default', item['id'])), 'errors': errors}
