"""Words that are never part of a person's name on a lab report: column headings, report terms,
units and common test names, in English and Russian. They keep the name finder off biomarker
rows (a biomarker row that's hidden by mistake isn't read by the AI). Normalized (`text.norm`).
"""

from .text import norm

_WORDS = """
result results value values unit units reference references range ranges interval norm normal
test tests analysis analyses parameter parameters flag flags comment comments note notes method
specimen sample material collected collection received reported report date time printed page
laboratory lab clinic hospital department center centre medical diagnostics diagnostic panel
profile status final preliminary verified approved signed high low positive negative detected
not none absent present blood serum plasma urine whole venous capillary fasting
patient doctor physician sex gender male female age years year old
information info details data demographics instructions preparation copy portal summary history
hemoglobin haemoglobin hematocrit haematocrit erythrocytes leukocytes platelets neutrophils
lymphocytes monocytes eosinophils basophils ferritin iron transferrin glucose insulin cholesterol
triglycerides lipoprotein creatinine urea bilirubin albumin protein globulin alanine aspartate
aminotransferase alkaline phosphatase gamma glutamyl sodium potassium calcium magnesium chloride
phosphorus zinc copper vitamin folate folic thyroid thyrotropin thyroxine triiodothyronine
cortisol testosterone estradiol progesterone prolactin hormone luteinizing follicle stimulating
antibodies antibody antigen reactive c-reactive sedimentation rate count mean corpuscular volume
concentration distribution width total free direct indirect hdl ldl vldl tsh alt ast ggt crp esr
rbc wbc plt mcv mch mchc rdw hba1c psa ige igg igm
результат результаты значение значения единицы единица референсные референсный интервал
диапазон норма нормы показатель показатели исследование исследования анализ анализы тест
метод комментарий примечание биоматериал материал образец проба дата время взятия забора
получения выдачи выполнения лаборатория лабораторный отделение клиника центр медицинский
медицинская диагностика панель профиль статус кровь сыворотка плазма моча венозная капиллярная
натощак пол мужской женский возраст лет год года пациент врач информация данные сведения памятка
гемоглобин гематокрит эритроциты лейкоциты тромбоциты нейтрофилы лимфоциты моноциты эозинофилы
базофилы ферритин железо трансферрин глюкоза инсулин холестерин триглицериды липопротеиды
липопротеины креатинин мочевина билирубин альбумин белок глобулин аланинаминотрансфераза
аспартатаминотрансфераза щелочная фосфатаза гамма глутамилтрансфераза натрий калий кальций
магний хлор фосфор цинк медь витамин фолиевая кислота тиреотропный гормон тироксин трийодтиронин
кортизол тестостерон эстрадиол прогестерон пролактин лютеинизирующий фолликулостимулирующий
антитела антиген реактивный с-реактивный скорость оседания количество средний средняя объем
концентрация распределения ширина общий общая свободный прямой непрямой лпвп лпнп ттг алт аст
ггт срб соэ
"""

STOPWORDS: frozenset[str] = frozenset(norm(w) for w in _WORDS.split())

#: Titles before or after a name, left out of a name's block.
TITLES: frozenset[str] = frozenset(
    norm(w)
    for w in [
        "dr",
        "dr.",
        "mr",
        "mrs",
        "ms",
        "miss",
        "prof",
        "md",
        "phd",
        "mbbs",
        "do",
        "rn",
        "np",
        "pa-c",
        "к.м.н",
        "д.м.н",
        "проф",
    ]
)
