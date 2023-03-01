import redis


class RedisClient:
    def __init__(self, config):
        self.redis_client = redis.Redis(
            host=config["redis"]["host"], port=config["redis"]["port"] or 6379
        )
        self.redis_list = config["redis"]["job_queue"]

    def get_length(self):
        return self.redis_client.llen(self.redis_list)

    def push(self, payload):
        if payload == None:
            return

        self.redis_client.lpush(self.redis_list, str(payload))
