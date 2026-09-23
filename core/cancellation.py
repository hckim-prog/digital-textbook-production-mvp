"""Cooperative cancellation at safe boundaries; never terminate a worker thread."""


class OperationCancelled(RuntimeError):
    pass


def check_cancelled(cancelled):
    if cancelled is not None and not callable(cancelled):
        raise ValueError('중단 상태는 확인 함수로 전달해야 합니다.')
    if cancelled and cancelled():
        raise OperationCancelled('사용자 요청으로 중단했습니다. 저장된 교정 결과는 다시 사용할 수 있습니다.')
