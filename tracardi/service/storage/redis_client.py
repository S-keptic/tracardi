import logging

import aioredis
import redis

from tracardi.exceptions.log_handler import log_handler
from tracardi.service.singleton import Singleton
from tracardi.config import redis_config, tracardi

logger = logging.getLogger(__name__)
logger.setLevel(tracardi.logging_level)
logger.addHandler(log_handler)


class AsyncRedisClient(metaclass=Singleton):
    def __init__(self):
        host = redis_config.redis_host
        password = redis_config.redis_password

        if password is None:
            self.client = aioredis.from_url(host)
        else:
            self.client = aioredis.from_url(host, password=password)

        logger.info(f"Redis at {host} connected.")


class RedisClient(metaclass=Singleton):
    def __init__(self):
        # host = redis_config.redis_host
        # password = redis_config.redis_password

        # if password is None:
        #     self.client = redis.from_url(redis_config.get_redis_with_password())
        # else:
        #     self.client = redis.from_url(host, password=password)
        uri = redis_config.get_redis_with_password()
        logger.debug(f"Connecting redis at {uri}")
        self.client = redis.from_url(uri)
        logger.info(f"Redis at {redis_config.redis_host} connected.")
