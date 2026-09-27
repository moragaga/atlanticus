# Separa fallos de adquisición de la semántica de findings B.2.
# Contrato AlarmCandidateAcquisitionError: mantiene invariantes de esta frontera.
class AlarmCandidateAcquisitionError(RuntimeError):
    pass


# Contrato AlarmCandidateUnavailableError: mantiene invariantes de esta frontera.
class AlarmCandidateUnavailableError(AlarmCandidateAcquisitionError):
    pass


# Contrato AlarmCandidateMismatchError: mantiene invariantes de esta frontera.
class AlarmCandidateMismatchError(AlarmCandidateAcquisitionError):
    pass


# Contrato AlarmCandidateContractError: mantiene invariantes de esta frontera.
class AlarmCandidateContractError(AlarmCandidateAcquisitionError):
    pass
