from app.worker import MAX_ATTEMPTS
def test_worker_attempts_are_bounded():
 assert MAX_ATTEMPTS==5
