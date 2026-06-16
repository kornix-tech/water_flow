export interface AnalyticalTestDefinition {
  name: string;
  label: string;
  title: string;
  description: string;
  analytical: string;
}

export interface AnalyticalTestGroup {
  title: string;
  description: string;
  tests: AnalyticalTestDefinition[];
}

export const analyticalTestGroups: AnalyticalTestGroup[] = [
  {
    title: "Служебный запуск",
    description: "Команда для запуска всего verification-suite одним заданием.",
    tests: [
      {
        name: "all",
        label: "Запустить все тесты",
        title: "Полный verification-suite",
        description:
          "Последовательно запускает все проверки ниже и собирает общий статус. Richards-тесты выполняют численное сравнение PFLOTRAN; Philip, Green-Ampt и Richards MMS дополнительно строят расчетные TECPLOT-профили PFLOTRAN, а постановки вне текущего Richards-стека остаются аналитическими эталонами до подключения соответствующей физики.",
        analytical:
          "Набор эталонов включает Дарси, гидростатику van Genuchten, unit-gradient drainage, manufactured storage, Theis, Ogata-Banks, Terzaghi, Philip, Green-Ampt, heat conduction, Buckley-Leverett, MMS Richards и Boussinesq."
      }
    ]
  },
  {
    title: "1D и пространственно-однородные benchmarks",
    description: "Вертикальные колонки, одномерные линейные задачи и lumped/manufactured-постановки без двумерной сетки.",
    tests: [
      {
        name: "tabular_full_demo",
        label: "Табличная почва",
        title: "Полный табличный расчет водоудерживания и влагопроводности",
        description:
          "Создает расчет в базе проекта, записывает табличные кривые Pc(S) и kr(S), запускает PFLOTRAN с LOOKUP_TABLE + PCHIP_LIQ и строит графики результата.",
        analytical:
          "Это smoke/contract-сценарий для пользовательских экспериментальных кривых: проверяется прохождение полного расчетного контура от формы и SQLite до TECPLOT-профилей PFLOTRAN."
      },
      {
        name: "linear_darcy",
        label: "Линейный Darcy",
        title: "Насыщенная колонка с постоянным потоком",
        description:
          "Проверяет, что численный расчет в насыщенной однородной колонке воспроизводит линейный профиль давления при постоянном потоке сверху и заданном нижнем давлении.",
        analytical:
          "Сравнение идет с аналитическим законом Дарси при K = Ks: поток qz задается градиентом полного напора, а давление P(z) является линейной функцией глубины."
      },
      {
        name: "hydrostatic_vg_no_flow",
        label: "Гидростатика VG",
        title: "Гидростатическое равновесие без потока",
        description:
          "Проверяет, что гидростатическое начальное состояние в однородной колонке с моделью насыщенности van Genuchten сохраняется при верхней и нижней границах no-flow.",
        analytical:
          "Численное давление сравнивается с P(z) = P_bottom - rho*g*z, насыщенность - с кривой van Genuchten Se(h), а реконструированный поток должен быть равен нулю."
      },
      {
        name: "unit_gradient_unsat",
        label: "Единичный градиент",
        title: "Установившийся ненасыщенный гравитационный дренаж",
        description:
          "Проверяет режим, где давление по колонке постоянно, градиент давления отсутствует, а поток возникает только из-за гравитации и относительной проницаемости.",
        analytical:
          "Сравнение выполняется с qz = -Ks*kr: kr считается по Mualem-van Genuchten из постоянного давления, а профиль давления и насыщенности должен оставаться пространственно постоянным."
      },
      {
        name: "transient_uniform_storage_vg",
        label: "Нестационарное хранение",
        title: "Manufactured-задача равномерного хранения",
        description:
          "Проверяет нестационарную реакцию горизонтальной no-flow области на равномерный SOURCE_SINK. Область должна оставаться пространственно однородной, а масса - следовать заданному закону хранения.",
        analytical:
          "Средняя насыщенность сравнивается с S(t) = S0 + A*(1 - cos(2*pi*t/T))/2, расход источника - с phi*V*dS/dt, давление - с обратной кривой van Genuchten h(S)."
      },
      {
        name: "brooks_corey_burdine",
        label: "Brooks-Corey + Burdine",
        title: "Гидростатика Brooks-Corey с Burdine kr",
        description:
          "Проверяет новую проверенную пару моделей водоудерживания и влагопроводности: Brooks-Corey для S(h) и Burdine для kr(Se) в no-flow колонке.",
        analytical:
          "Давление сравнивается с гидростатикой P(z)=P_bottom-rho*g*z, насыщенность - с Brooks-Corey Se(h), а поток должен оставаться нулевым."
      },
      {
        name: "ogata_banks_1d_transport",
        label: "Ogata-Banks transport",
        title: "Одномерная адвекция-дисперсия",
        description:
          "Готовит эталон для будущего transport-модуля: фронт растворенного вещества в полуограниченной области при постоянной входной концентрации.",
        analytical: "Классическое решение Ogata-Banks через erfc-члены для адвекции-дисперсии."
      },
      {
        name: "terzaghi_1d_consolidation",
        label: "Terzaghi consolidation",
        title: "Одномерная консолидация",
        description: "Готовит эталон для проверки storage/compressibility и рассеивания избыточного порового давления.",
        analytical: "Рядовое решение Terzaghi для дренированной одномерной колонки."
      },
      {
        name: "philip_infiltration",
        label: "Philip infiltration",
        title: "Ранняя стадия инфильтрации",
        description: "Готовит полуаналитический benchmark инфильтрации и запускает Richards-колонку PFLOTRAN для получения расчетных профилей влажности и давления.",
        analytical: "Приближение Philip: I(t)=S*sqrt(t)+A*t и производная скорость инфильтрации."
      },
      {
        name: "green_ampt_infiltration",
        label: "Green-Ampt",
        title: "Инфильтрация с резким фронтом",
        description: "Готовит инженерный benchmark накопленной инфильтрации и запускает Richards-колонку PFLOTRAN с верхним инфильтрационным потоком.",
        analytical: "Неявное решение Green-Ampt: F - psi*DeltaTheta*ln(1+F/(psi*DeltaTheta)) = Ks*t."
      },
      {
        name: "heat_conduction_1d",
        label: "Heat conduction",
        title: "Одномерная теплопроводность",
        description: "Готовит эталон для будущей проверки диффузионного оператора и временной схемы в heat/energy модуле.",
        analytical: "erfc-решение для полуограниченного тела со ступенчатой температурой поверхности."
      },
      {
        name: "buckley_leverett",
        label: "Buckley-Leverett",
        title: "Двухфазное вытеснение",
        description: "Готовит эталон fractional-flow для будущего двухфазного модуля и shock/front propagation.",
        analytical: "Buckley-Leverett на Corey-кривых относительной проницаемости и фракционном потоке воды."
      },
      {
        name: "richards_mms",
        label: "Richards MMS",
        title: "Manufactured solution для Richards",
        description: "Готовит гладкий MMS-профиль напора и запускает PFLOTRAN как профильный расчетный carrier для проверки вывода Richards-снимков.",
        analytical: "Задан h(z,t)=h0+A*sin(pi*z/L)*exp(-t/tau); source term должен выводиться из выбранной формы h."
      }
    ]
  },
  {
    title: "2D, радиальные и профильные benchmarks",
    description: "Постановки, где физический смысл связан с радиальным или профильным распределением в плане/разрезе.",
    tests: [
      {
        name: "theis_radial_flow",
        label: "Theis radial flow",
        title: "Радиальный приток к скважине",
        description:
          "Готовит эталон для насыщенного радиального потока к скважине и проверки transmissivity/storage, знака дебита и единиц времени. Это радиальная 2D/axisymmetric постановка.",
        analytical: "Theis: s(r,t)=Q/(4*pi*T)*W(u), где u=r^2*S/(4*T*t), W(u) - экспоненциальный интеграл."
      },
      {
        name: "boussinesq_groundwater_mound",
        label: "Boussinesq mound",
        title: "Бугор уровня грунтовых вод",
        description:
          "Готовит эталон для нестационарного затухания возмущения уровня грунтовых вод в линеаризованной модели Boussinesq. Это профильная groundwater-постановка для разреза/плана.",
        analytical: "Синусоидальный mound h(x,t)=h0+A*sin(pi*x/L)*exp(-D*(pi/L)^2*t)."
      }
    ]
  }
];
