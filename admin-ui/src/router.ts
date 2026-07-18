import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import UsersView from '@/views/UsersView.vue'
import CandidatesView from '@/views/CandidatesView.vue'
import NominationsView from '@/views/NominationsView.vue'
import QuestionnaireView from '@/views/QuestionnaireView.vue'
import SyncView from '@/views/SyncView.vue'
import LogsView from '@/views/LogsView.vue'
import ExportView from '@/views/ExportView.vue'
import OverviewView from '@/views/monitor/OverviewView.vue'
import ClustersView from '@/views/monitor/ClustersView.vue'
import SuspectsView from '@/views/monitor/SuspectsView.vue'
import VotesView from '@/views/monitor/VotesView.vue'
import AccountView from '@/views/monitor/AccountView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: DashboardView },
  { path: '/users', component: UsersView },
  { path: '/candidates', component: CandidatesView },
  { path: '/nominations', component: NominationsView },
  { path: '/questionnaires', component: QuestionnaireView },
  { path: '/sync', component: SyncView },
  { path: '/logs', component: LogsView },
  { path: '/export', component: ExportView },
  { path: '/monitor/overview', component: OverviewView },
  { path: '/monitor/clusters', component: ClustersView },
  { path: '/monitor/suspects', component: SuspectsView },
  { path: '/monitor/votes', component: VotesView },
  { path: '/monitor/account/:voteId', component: AccountView, props: true },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
