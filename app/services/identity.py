"""Bilingual user names without altering existing users.full_name columns.

Legacy records continue using `users.full_name` (Arabic/canonical); English
names are optional until those users edit their profiles.
"""
from app.models.user import UserNameTranslation


def set_english_name(user, name_en):
    if name_en is None:
        return
    cleaned = ' '.join(name_en.split())
    if cleaned:
        if user.name_translation:
            user.name_translation.full_name_en = cleaned
        else:
            user.name_translation = UserNameTranslation(full_name_en=cleaned)
    elif user.name_translation:
        user.name_translation = None
