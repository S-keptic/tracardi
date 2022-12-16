import json
import logging
from datetime import datetime
from hashlib import sha1
from typing import Optional, List, Tuple, Any, Union
from uuid import uuid4

from pydantic import BaseModel, PrivateAttr
from tracardi.config import tracardi

from ..entity import Entity
from ..event_metadata import EventPayloadMetadata
from ..event_source import EventSource
from ..payload.event_payload import EventPayload
from ..profile import Profile
from ..session import Session, SessionMetadata, SessionTime
from ..time import Time
from ...exceptions.log_handler import log_handler
# from ...service.cache_manager import CacheManager

logger = logging.getLogger(__name__)
logger.setLevel(tracardi.logging_level)
logger.addHandler(log_handler)
# TODO remove circular dep
# cache = CacheManager()


class TrackerPayload(BaseModel):

    _id: str = PrivateAttr(None)

    source: Union[EventSource, Entity]  # When read from a API then it is Entity then is replaced by EventSource
    session: Optional[Entity] = None

    metadata: Optional[EventPayloadMetadata]
    profile: Optional[Entity] = None
    context: Optional[dict] = {}
    properties: Optional[dict] = {}
    request: Optional[dict] = {}
    events: List[EventPayload] = []
    options: Optional[dict] = {}
    profile_less: bool = False

    def __init__(self, **data: Any):
        data['metadata'] = EventPayloadMetadata(
            time=Time(
                insert=datetime.utcnow()
            ))
        super().__init__(**data)
        self._id = str(uuid4())

    def set_headers(self, headers: dict):
        if 'authorization' in headers:
            del headers['authorization']
        if 'cookie' in headers:
            del headers['cookie']
        self.request['headers'] = headers

    def get_id(self) -> str:
        return self._id

    def get_finger_print(self) -> str:
        jdump = json.dumps(self.dict(exclude={'events': ..., 'metadata': ...}), sort_keys=True, default=str)
        props_hash = sha1(jdump.encode())
        return props_hash.hexdigest()

    # TODO remove after 2023-01-01
    # def get_events(self, session: Optional[Session], profile: Optional[Profile], has_profile) -> List[Event]:
    #     event_list = []
    #     if self.events:
    #         debugging = self.is_debugging_on()
    #         for event in self.events:  # type: EventPayload
    #             _event = event.to_event(self.metadata, self.source, session, profile, has_profile)
    #             _event.metadata.status = COLLECTED
    #             _event.metadata.debug = debugging
    #
    #             # Append session data
    #             if isinstance(session, Session):
    #                 _event.session.start = session.metadata.time.insert
    #                 _event.session.duration = session.metadata.time.duration
    #
    #             # Add tracker payload properties as event request values
    #
    #             if isinstance(_event.request, dict):
    #                 _event.request.update(self.request)
    #             else:
    #                 _event.request = self.request
    #
    #             event_list.append(_event)
    #     return event_list

    def set_return_profile(self, source: EventSource):
        if source.returns_profile is False:
            self.options.update({
                "profile": False
            })

    def set_transitional(self, source: EventSource):
        if source.transitional is True:
            self.options.update({
                "saveSession": False,
                "saveEvents": False
            })

    def force_session(self, session):
        # Get session
        if self.session is None or self.session.id is None:
            # Generate random
            self.session = session

    def return_profile(self):
        return self.options and "profile" in self.options and self.options['profile'] is True

    def is_on(self, key, default):
        if key not in self.options or not isinstance(self.options[key], bool):
            # default value
            return default

        return self.options[key]

    def is_debugging_on(self) -> bool:
        return tracardi.track_debug and self.is_on('debugger', default=False)

    async def get_static_profile_and_session(self, session: Session, load_merged_profile, profile_less) -> Tuple[
        Optional[Profile], Session]:

        if profile_less:
            profile = None
        else:
            if not self.profile.id:
                raise ValueError("Can not use static profile id without profile.id.")

            profile = await load_merged_profile(self.profile.id)
            if not profile:
                profile = Profile(
                    id=self.profile.id
                )
                profile.operation.new = True

            if session is None:
                session = Session(
                    id=self.session.id,
                    metadata=SessionMetadata(
                        time=SessionTime(
                            insert=datetime.utcnow()
                        )
                    )
                )
                session.operation.new = True

                # # Remove the session from cache we just created one.
                # # We repeat it when saving.
                # cache.session_cache().delete(self.session.id)

        return profile, session

    async def get_profile_and_session(self, session: Session, load_merged_profile, profile_less) -> Tuple[
        Optional[Profile], Session]:

        """
        Returns session. Creates profile if it does not exist.If it exists connects session with profile.
        """

        is_new_profile = False
        is_new_session = False
        profile = None

        if session is None:  # loaded session is empty

            session = Session(
                id=self.session.id,
                metadata=SessionMetadata(
                    time=SessionTime(
                        insert=datetime.utcnow()
                    )
                )
            )

            logger.debug("New session is to be created with id {}".format(session.id))

            is_new_session = True

            if profile_less is False:

                # Bind profile
                if self.profile is None:

                    # Create empty default profile generate profile_id
                    profile = Profile.new()

                    # Create new profile
                    is_new_profile = True

                    logger.info(
                        "New profile created at UTC {} with id {}".format(profile.metadata.time.insert, profile.id))

                else:

                    # ID exists, load profile from storage
                    profile = await load_merged_profile(id=self.profile.id)  # type: Profile

                    if profile is None:
                        # Profile id delivered but profile does not exist in storage.
                        # ID was forged

                        profile = Profile.new()

                        # Create new profile
                        is_new_profile = True

                        logger.info(
                            "No merged profile. New profile created at UTC {} with id {}".format(
                                profile.metadata.time.insert,
                                profile.id))

                    else:
                        logger.info(
                            "Merged profile loaded with date {} UTC and id {}".format(profile.metadata.time.insert,
                                                                                      profile.id))

                # Now we have profile and we should assign it to session

                session.profile = Entity(id=profile.id)

        else:

            logger.info("Session exists with id {}".format(session.id))

            if profile_less is False:

                # There is session. Copy profile id form session to profile

                if session.profile is not None:
                    # Loaded session has profile

                    # Load profile based on profile id saved in session
                    profile = await load_merged_profile(id=session.profile.id)  # type: Profile

                    if isinstance(profile, Profile) and session.profile.id != profile.id:
                        # Profile in session id has been merged. Change profile in session.

                        session.profile.id = profile.id
                        session.metadata.time.timestamp = datetime.timestamp(datetime.utcnow())

                        is_new_session = True

                else:
                    # Corrupted session, or profile less session

                    profile = None

                # Although we tried to load profile it still does not exist.
                if profile is None:
                    # ID exists but profile not exist in storage.

                    profile = Profile.new()

                    # Create new profile
                    is_new_profile = True

                    # Update session as there is new profile. Previous session had no profile.id.
                    session.profile = Entity(id=profile.id)
                    is_new_session = True

        if isinstance(session.context, dict):
            session.context.update(self.context)
        else:
            session.context = self.context

        if isinstance(session.properties, dict):
            session.properties.update(self.properties)
        else:
            session.properties = self.properties

        session.operation.new = is_new_session

        if profile_less is False and profile is not None:
            profile.operation.new = is_new_profile

        return profile, session
