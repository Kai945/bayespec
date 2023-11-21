from elisa.inference.fit import MaxLikeFit, BayesianFit
from elisa.model.add import Powerlaw
from elisa.data.ogip import Data


m = Powerlaw()

MaxLikeFit([Data([1, 20], '')], m, ['chi2'])
