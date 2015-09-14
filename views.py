import json

from django.views.generic import View, TemplateView, ListView, FormView
from django.views.generic.edit import CreateView
from django.views.decorators.csrf import requires_csrf_token
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.core.urlresolvers import reverse
from django import http
from django.http import JsonResponse

from rest_framework import viewsets, pagination
from djcelery.models import TaskMeta
from celery import states

from models import Match, Item, Hero, ScikitModel, MatchPrediction
from serializers import UserSerializer, GroupSerializer, HeroSerializer, \
    MatchSerializer, ItemSerializer, HeroRecentMatchesSerializer, MatchDateCountSerializer, ItemRecentMatchSerializer, \
    TaskMetaSerializer
from forms import PredictionForm, ModelTestForm
from scikit import DotaModel
from dota import DotaApi


class LoginRequiredMixin(object):
    @classmethod
    def as_view(cls, *args, **kwargs):
        view = super(LoginRequiredMixin, cls).as_view(*args, **kwargs)
        return login_required(view)


class JSONResponseMixin(object):
    def render_to_json_response(self, context, **kwargs):
        return http.JsonResponse(
            self.get_data(context),
            **kwargs
        )

    def get_data(self, context):
        del context['view']
        return context


class JSONView(JSONResponseMixin, TemplateView):
    def render_to_response(self, context, **response_kwargs):
        return self.render_to_json_response(context, **response_kwargs)


class IndexView(TemplateView):
    template_name = 'DotaStats/index.html'

    def get_context_data(self, **kwargs):
        self.request.META["CSRF_COOKIE_USED"] = True #force csrf cookie
        return super(IndexView, self).get_context_data(**kwargs)

    @method_decorator(requires_csrf_token)
    def dispatch(self, *args, **kwargs):
        return super(IndexView, self).dispatch(*args, **kwargs)


class AdminView(TemplateView):
    template_name = 'DotaStats/admin.html'

    def get_context_data(self, **kwargs):
        context = super(AdminView, self).get_context_data(**kwargs)
        context['count'] = Match.get_all().filter(valid_for_model=True).count()
        context['heroes'] = Hero.get_serialized_hero_list()
        return context


class AjaxLoadMatchesFromAPI(LoginRequiredMixin, JSONView):
    def get_context_data(self, **kwargs):
        return super(AjaxLoadMatchesFromAPI, self).get_context_data(
            status=DotaApi.load_matches_from_api(), **kwargs)


class AjaxLoadStaticDataView(LoginRequiredMixin, JSONView):
    def get_context_data(self, **kwargs):
        return super(AjaxLoadStaticDataView, self).get_context_data(heroes=DotaApi.load_heroes_from_api(),
                                                                    items=DotaApi.load_items_from_api(),
                                                                    attributes=DotaApi.load_hero_attribute_from_api(),
                                                                    **kwargs)


class BuildDataView(View):
    @staticmethod
    def get(request):
        model = ScikitModel.create_model()
        return http.HttpResponse(json.dumps({'task_id': model.task_id}))


class BuildAndTestView(TemplateView):
    template_name = 'DotaStats/build.html'

    def get_context_data(self, **kwargs):
        context = super(BuildAndTestView, self).get_context_data(**kwargs)
        form = ModelTestForm(self.request.GET)
        context['form'] = form
        DotaModel.mapreduce()

        if form.is_valid():
            # data = form.cleaned_data
            # context['count'], context['accuracy'], context['radiant_win']\
            #     = DotaModel.build(data['n_matches'], data['n_tests'], data['min_duration'], data['algorithm'])
            context['valid'] = True
        else:
            context['valid'] = False
        return context


class HeroListView(ListView):
    template_name = 'DotaStats/herolist.html'
    context_object_name = 'heroes'

    def get_queryset(self):
        return Hero.objects.filter(hero_id__gt=0).order_by('primary_attribute')


class ItemListView(ListView):
    template_name = 'DotaStats/itemlist.html'
    context_object_name = 'items'
    model = Item

    def get_queryset(self):
        return super(ItemListView, self).get_queryset().filter(item_id__gt=0)


class MatchListView(ListView):
    template_name = 'DotaStats/matchlist.html'
    context_object_name = 'matches'
    model = Match
    paginate_by = 50

    def get_queryset(self):
        return super(MatchListView, self).get_queryset().filter(valid_for_model=True).order_by('-match_id') \
            .prefetch_related('playerinmatch', 'playerinmatch__hero')


class CreatePredictionView(CreateView):
    template_name = 'DotaStats/predict.html'
    form_class = PredictionForm
    context_object_name = 'form'

    def get_success_url(self):
        self.object.get_prediction()
        return reverse('index')

    def get_context_data(self, **kwargs):
        context = super(CreatePredictionView, self).get_context_data(**kwargs)
        context['predictions'] = MatchPrediction.objects.all()
        return context


class LogInView(FormView):
    template_name = 'DotaStats/login.html'
    form_class = AuthenticationForm

    def post(self, request, *args, **kwargs):
        print request.body
        print request.POST
        print request.POST.get('username')
        print request.POST.get('password')
        return super(LogInView, self).post(self, request, *args, **kwargs)

    def form_valid(self, form, **kwargs):
        form.clean()
        user = form.get_user()
        if user is not None:
            login(self.request, user)
            return JsonResponse({
                'user': user.username,
                'errors': False
            })
        else:
            return JsonResponse({
                'user': '',
                'errors': True
            })

    def form_invalid(self, form, **kwargs):
        super(LogInView, self).form_invalid(form)
        return JsonResponse({'user':False, 'errors':form.errors}, status=400)


class LogOutView(View):
    def get(self, request):
        logout(request)
        return redirect(reverse('index'))


class StandardResultsSetPagination(pagination.PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 25


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class HeroViewSet(viewsets.ModelViewSet):
    queryset = Hero.objects.all().filter(hero_id__gt=0)
    serializer_class = HeroSerializer


class HeroRecentMatchesSet(viewsets.ModelViewSet):
    queryset = Hero.objects.all().filter(hero_id__gt=0)
    serializer_class = HeroRecentMatchesSerializer


class MatchViewSet(viewsets.ModelViewSet):
    queryset = Match.objects.all().filter(valid_for_model=True).order_by('-match_id') \
        .prefetch_related('playerinmatch',
                          'playerinmatch__hero',
                          'playerinmatch__item_0',
                          'playerinmatch__item_1',
                          'playerinmatch__item_2',
                          'playerinmatch__item_3',
                          'playerinmatch__item_4',
                          'playerinmatch__item_5')
    serializer_class = MatchSerializer
    pagination_class = StandardResultsSetPagination


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().filter(item_id__gt=0, recipe=False).order_by('item_id')
    serializer_class = ItemSerializer


class MatchDateCountSet(viewsets.ModelViewSet):
    queryset = Match.get_count_by_date_set()
    serializer_class = MatchDateCountSerializer


class ItemRecentMatchSet(viewsets.ModelViewSet):
    queryset = Item.objects.all().filter(item_id__gt=0)
    serializer_class = ItemRecentMatchSerializer


class TaskMetaSet(viewsets.ModelViewSet):
    serializer_class = TaskMetaSerializer

    def get_queryset(self):
        status = self.request.query_params.get('status', None)
        if status is not None and status in states.ALL_STATES:
            return TaskMeta.objects.all().order_by('-id').filter(status=status)[:100]
        else:
            return TaskMeta.objects.all().order_by('-id')[:100]

