# from organise_date_folders import process_date
import organise_date_folders as odf
import pytest


def test_get_photo_monthly_folder_path_correct_date1():
    assert odf.get_photo_monthly_folder_path("2018-10-01") == r"h:\\__ Photos\2018\10. October"
def test_get_photo_monthly_folder_path_correct_date2():
    assert odf.get_photo_monthly_folder_path("2018-10-01") == r"h:\\__ Photos\2018\10. October"

def test_get_photo_monthly_folder_path_incorrect_date1():
    with pytest.raises(AssertionError):
        odf.get_photo_monthly_folder_path("2018-10-401")

def test_get_photo_monthly_folder_path_incorrect_date2():
    with pytest.raises(AssertionError):
        odf.get_photo_monthly_folder_path("2018=10-01")

def test_get_photo_monthly_folder_path_incorrect_date3():
    with pytest.raises(AssertionError):
        odf.get_photo_monthly_folder_path(2018)

def test_get_photo_monthly_folder_path_incorrect_date4():
    with pytest.raises(AssertionError) as e_info:
        odf.get_photo_monthly_folder_path(2018)
        # e_info saves the exception object so you can extract details from it. For example,
        # if you want to check the exception call stack or another nested exception inside.
        # (didn't show any message)
        print e_info
