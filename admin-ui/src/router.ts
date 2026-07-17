import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import UsersView from '@/views/UsersView.vue'
import OverviewView from '@/views/monitor/OverviewView.vue'
import ClustersView from '@/views/monitor/ClustersView.vue'
import SuspectsView from '@/views/monitor/SuspectsView.vue'
import VotesView from '@/views/monitor/VotesView.vue'
import AccountView from '@/views/monitor/AccountView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: DashboardView },
  { path: '/users', component: UsersView },
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
