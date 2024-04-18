DATA_STORAGE = "/symphony_data"

INTAKE_PAYLOAD_BYTES_MAX_SIZE = 10485760  # 10 Mio bytes
# define the factor to compute the maximum byte size of chunk
# from the maximum byte size of the payload.
# This factor should consider the json envelop (64b)
# and the escapement of the characters
CHUNK_BYTES_FACTOR = 0.9
CHUNK_BYTES_MAX_SIZE = int(INTAKE_PAYLOAD_BYTES_MAX_SIZE * CHUNK_BYTES_FACTOR)
EVENT_BYTES_MAX_SIZE = 250000
