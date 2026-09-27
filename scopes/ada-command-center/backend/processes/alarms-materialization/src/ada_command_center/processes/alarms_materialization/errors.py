class AlarmCandidateAcquisitionError(RuntimeError):
    pass


class AlarmCandidateUnavailableError(AlarmCandidateAcquisitionError):
    pass


class AlarmCandidateMismatchError(AlarmCandidateAcquisitionError):
    pass


class AlarmCandidateContractError(AlarmCandidateAcquisitionError):
    pass
