# -*- coding: utf-8 -*-
"""Czysta logika dopasowywania aktywności do treningu z planu."""


def find_activity_for_workout(*, workout, activities):
    """Zwróć wybraną aktywność (albo ``None``) oraz metodę dopasowania.

    Id wskazane w planie ma pierwszeństwo przed dopasowaniem heurystycznym.
    """
    requested_id = workout.get('matched_activity_id')
    if requested_id is not None:
        matched_activity = next(
            (activity for activity in activities
             if activity.get('activity_id') is not None
             and str(activity.get('activity_id')) == str(requested_id)),
            None,
        )
        if matched_activity is not None:
            return matched_activity, 'id'

    day_activities = [
        activity for activity in activities
        if activity.get('date', '')[:10] == workout['date']
        and activity.get('type', '').startswith('running')
    ]
    if not day_activities:
        return None, 'unmatched'

    target_distance = workout.get('distance_km')
    target_name = (workout.get('name') or '').strip().lower()
    ranked = []
    for activity in day_activities:
        distance = activity.get('distance_km')
        distance_diff = (
            abs(distance - target_distance)
            if isinstance(distance, (int, float))
            and isinstance(target_distance, (int, float))
            else 0
        )
        name = (activity.get('name') or '').strip().lower()
        name_score = 2 if name == target_name else 1 if target_name and target_name in name else 0
        ranked.append((distance_diff, -name_score, activity))

    ranked.sort(key=lambda item: (item[0], item[1]))
    best = ranked[0]
    if sum((item[0], item[1]) == (best[0], best[1]) for item in ranked) != 1:
        return None, 'ambiguous'
    return best[2], 'heuristic'


def assign_activities(*, workouts, activities):
    """Przypisz biegi do treningów bez wielokrotnego zaliczania aktywności.

    Kluczem wyniku jest pozycja treningu w przekazanej liście, a wartością
    jest para ``(aktywność albo None, metoda_dopasowania)``.
    """
    result = {index: (None, 'unmatched') for index, _ in enumerate(workouts)}
    reserved_ids = set()
    activities_by_id = {
        activity.get('activity_id'): activity for activity in activities
        if activity.get('activity_id') is not None
    }

    for index, workout in enumerate(workouts):
        requested_id = workout.get('activity_id')
        activity = activities_by_id.get(requested_id)
        if (activity is not None
                and activity.get('date', '')[:10] == workout.get('date')
                and activity.get('type', '').startswith('running')
                and requested_id not in reserved_ids):
            result[index] = (activity, 'id')
            reserved_ids.add(requested_id)

    choices = {}
    for index, workout in enumerate(workouts):
        if result[index][0] is not None:
            continue
        target_distance = workout.get('distance_km')
        target_name = (workout.get('name') or '').strip().lower()
        ranked = []
        for activity in activities:
            activity_id = activity.get('activity_id')
            if (activity_id in reserved_ids
                    or activity.get('date', '')[:10] != workout.get('date')
                    or not activity.get('type', '').startswith('running')):
                continue
            distance = activity.get('distance_km')
            name = (activity.get('name') or '').strip().lower()
            name_score = 2 if name == target_name else 1 if target_name and target_name in name else 0
            has_distance = isinstance(distance, (int, float)) and isinstance(target_distance, (int, float))
            if not has_distance and not name_score:
                continue
            distance_diff = abs(distance - target_distance) if has_distance else float('inf')
            ranked.append((distance_diff, -name_score, activity))
        if not ranked:
            continue
        ranked.sort(key=lambda item: (item[0], item[1]))
        best = ranked[0]
        if sum((item[0], item[1]) == (best[0], best[1]) for item in ranked) != 1:
            result[index] = (None, 'ambiguous')
        else:
            choices[index] = best[2]

    contenders = {}
    for index, activity in choices.items():
        contenders.setdefault(activity.get('activity_id'), []).append(index)
    for activity_id, indexes in contenders.items():
        if len(indexes) == 1:
            index = indexes[0]
            result[index] = (choices[index], 'heuristic')
            reserved_ids.add(activity_id)
        else:
            for index in indexes:
                result[index] = (None, 'ambiguous')
    return result
