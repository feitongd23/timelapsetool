export default defineAppConfig({
  pages: ['pages/login/index', 'pages/index/index', 'pages/report/index'],
  window: {
    navigationBarTitleText: '火烧云',
    navigationBarBackgroundColor: '#eef1f6',
    navigationBarTextStyle: 'black',
    backgroundColor: '#eef1f6'
  },
  permission: {
    'scope.userLocation': { desc: '用于按你的位置给出更准的火烧云质量和概率' }
  },
  requiredPrivateInfos: ['getLocation']
})
