__author__ = 'Robert Waltham'
import numpy as np
import numpy.random as random
from sklearn import svm, preprocessing, neighbors
from DotaStats.models import Match, ScikitModel, Hero
import json
import time

from contextlib import contextmanager

@contextmanager
def timeit_context(name):
    startTime = time.time()
    yield
    elapsedTime = time.time() - startTime
    print('[{}] finished in {} ms'.format(name, int(elapsedTime * 1000)))


class DotaModel():

    def __init__(self):
        pass

    @staticmethod
    def build():
        n_tests = 100
        n_heroes = Hero.objects.all().count()

        with timeit_context('Querying Matches'):
            matches = list(Match.objects.filter(has_been_processed=True)[:1000].prefetch_related('playerinmatch'))

        with timeit_context('Shuffling Matches'):
            random.shuffle(matches)

        match_features = []
        match_win = []

        with timeit_context('Building Data'):
            for match in matches:
                match_data, win = match.get_data_array(n_heroes)
                if match_data is not None:
                    match_features.append(match_data)
                    match_win.append(win)

        with timeit_context('Building Model'):
            clf = svm.SVC()
            clf.fit(match_features[n_tests:], match_win[n_tests:])

        with timeit_context('Scoring Model'):
            score = clf.score(match_features[:n_tests], match_win[:n_tests]) * 100

        return len(matches), score


    @staticmethod
    def build_and_store(n_matches, scikit_model_id):
        matches = list(Match.objects.filter(has_been_processed=True)[:n_matches])
        model, created = ScikitModel.objects.get_or_create(id=scikit_model_id)

        clf = svm.SVC()
        match_features = []
        match_win = []

        for match in matches:
            match_data, win = match.get_data_array()
            match_features.append(match_data)
            match_win.append(win)

        clf.fit(match_features, match_win)
        model.picked_model = clf
        model.match_count = n_matches
        model.is_ready = True
        model.save()
        return model.id

    @staticmethod
    def predict(scikit_model_id, match_data):
        return ScikitModel.objects.get(id=scikit_model_id).picked_model.predict(match_data)[0]

    @staticmethod
    def build_and_test(starting_match_id, test_match_ids):
        matches = Match.objects.filter(match_id__lt=starting_match_id)
        model = ScikitModel()

        match_win = np.array([])
        match_features = np.array([])
        for match in matches:
            match_data, win = match.get_data_array()
            np.append(match_features, match_data)
            np.append(match_win, win)


        results = []
        # clf = svm.SVC()
        # match_features = []
        # match_win = []
        #
        # for match in matches:
        #     match_data, win = match.get_data_array()
        #     match_features.append(match_data)
        #     match_win.append(win)
        #
        # clf.fit(match_features, match_win)
        # model.picked_model = clf
        # model.match_count = len(matches)
        # model.is_ready = True
        # model.save()
        #
        # results = []
        # test_matches = []
        # for match_id in test_match_ids:
        #     test_matches.append(Match.objects.get(match_id=match_id))
        #
        # for match in test_matches:
        #     match_data, win = match.get_data_array()
        #     prediction = clf.predict(match_data)[0]
        #     results.append({'prediction': prediction, 'win': win, 'match_id': match.match_id})
        return results



