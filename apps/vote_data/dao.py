"""Vote data access objects."""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.vote_data.models import Character, Cp, Music, Questionnaire


class VoteDataDAO:
    """Data access object for vote data operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # Character operations
    async def get_character_by_id(self, user_id: str) -> Character | None:
        """Get character data by user ID."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(Character).where(Character.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_character(self, character: Character) -> Character:
        """Create character vote data."""
        self.session.add(character)
        await self.session.commit()
        await self.session.refresh(character)
        return character

    async def update_character(self, user_id: str, character_list: list) -> Character | None:
        """Update character vote data."""
        from datetime import datetime
        character = await self.get_character_by_id(user_id)
        if character:
            character.character_list = character_list
            character.submit_datetime = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(character)
        return character

    # Music operations
    async def get_music_by_id(self, user_id: str) -> Music | None:
        """Get music data by user ID."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(Music).where(Music.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_music(self, music: Music) -> Music:
        """Create music vote data."""
        self.session.add(music)
        await self.session.commit()
        await self.session.refresh(music)
        return music

    async def update_music(self, user_id: str, music_list: list) -> Music | None:
        """Update music vote data."""
        from datetime import datetime
        music = await self.get_music_by_id(user_id)
        if music:
            music.music_list = music_list
            music.submit_datetime = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(music)
        return music

    # CP operations
    async def get_cp_by_id(self, user_id: str) -> Cp | None:
        """Get CP data by user ID."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(Cp).where(Cp.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_cp(self, cp: Cp) -> Cp:
        """Create CP vote data."""
        self.session.add(cp)
        await self.session.commit()
        await self.session.refresh(cp)
        return cp

    async def update_cp(self, user_id: str, cp_list: list) -> Cp | None:
        """Update CP vote data."""
        from datetime import datetime
        cp = await self.get_cp_by_id(user_id)
        if cp:
            cp.cp_list = cp_list
            cp.submit_datetime = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(cp)
        return cp

    # Questionnaire operations
    async def get_questionnaire_by_id(self, user_id: str) -> Questionnaire | None:
        """Get questionnaire data by user ID."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(Questionnaire).where(Questionnaire.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_questionnaire(self, questionnaire: Questionnaire) -> Questionnaire:
        """Create questionnaire vote data."""
        self.session.add(questionnaire)
        await self.session.commit()
        await self.session.refresh(questionnaire)
        return questionnaire

    async def update_questionnaire(
        self, user_id: str, questionnaire_list: list
    ) -> Questionnaire | None:
        """Update questionnaire vote data."""
        from datetime import datetime
        questionnaire = await self.get_questionnaire_by_id(user_id)
        if questionnaire:
            questionnaire.questionnaire_list = questionnaire_list
            questionnaire.submit_datetime = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(questionnaire)
        return questionnaire

    # Batch operations
    async def get_all_character_submissions(self) -> list[Character]:
        """Get all character submissions."""
        from sqlalchemy import select
        result = await self.session.execute(select(Character))
        return list(result.scalars().all())

    async def get_all_music_submissions(self) -> list[Music]:
        """Get all music submissions."""
        from sqlalchemy import select
        result = await self.session.execute(select(Music))
        return list(result.scalars().all())

    async def get_all_cp_submissions(self) -> list[Cp]:
        """Get all CP submissions."""
        from sqlalchemy import select
        result = await self.session.execute(select(Cp))
        return list(result.scalars().all())
