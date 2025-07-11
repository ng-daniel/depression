import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, f1_score, precision_recall_fscore_support, matthews_corrcoef

LABELS = ['model_name', 'note', 'loss', 'acc', 'prec0', 'prec1', 'rec0', 'rec1', 'f1sc0', 'f1sc1', 'sup0', 'sup1']

def eval_model(model: torch.nn, dataloader: DataLoader, criterion: torch.nn, device, note:str=None):
    '''
    Evaluate pytorch model performance on the test dataset.

    Args
    - model - pytorch nn model
    - dataloader - test data
    - criterion - loss function
    - device - 'cpu' or 'cuda'
    - note - miscelaneous information about the evaluation

    Returns
    - a series containing model results with loss, accuracy, precision, recall, f1score, and number of samples per class 
    '''
    test_loss = 0
    test_acc = 0
    test_precision = [0 for _ in range(2)]
    test_recall = [0 for _ in range(2)]
    test_fscore = [0 for _ in range(2)]
    test_support = [0 for _ in range(2)]
    test_mcc = 0

    model_name = type(model).__name__
    
    model.eval()
    with torch.inference_mode():
        for _, (X, y) in enumerate(dataloader):
            X, y = X.to(device), y.to(device)

            # forward pass
            out = model(X)
            preds = out.squeeze().sigmoid().round()

            # calculate loss
            loss = criterion(out.squeeze(), y)

            # aggregate metrics
            test_loss += loss.item()
            test_acc += ((preds==y).sum() / len(y)).item()

            precision, recall, fscore, support = precision_recall_fscore_support(y.cpu(), preds.cpu(), zero_division=np.nan)
            
            test_precision[0] += precision[0] if len(precision) > 0 else 0
            test_precision[1] += precision[1] if len(precision) > 1 else 0
            test_recall[0] += recall[0] if len(recall) > 0 else 0
            test_recall[1] += recall[1] if len(recall) > 1 else 0
            test_fscore[0] += fscore[0] if len(fscore) > 0 else 0
            test_fscore[1] += fscore[1] if len(fscore) > 1 else 0
            test_support[0] += support[0] if len(support) > 0  else 0
            test_support[1] += support[1] if len(support) > 1  else 0

            test_mcc += matthews_corrcoef(y.cpu(), preds.cpu())

    # calculate average metrics
    test_loss /= len(dataloader)
    test_acc /= len(dataloader)
    test_precision[0] /= len(dataloader)
    test_precision[1] /= len(dataloader)
    test_recall[0] /= len(dataloader)
    test_recall[1] /= len(dataloader)
    test_fscore[0] /= len(dataloader)
    test_fscore[1] /= len(dataloader)
    test_mcc /= len(dataloader)

    LABELS = ['model_name', 'note', 'loss', 'acc', 'prec0', 'prec1', 'rec0', 'rec1', 'f1sc0', 'f1sc1', 'sup0', 'sup1', 'mcc']
    results = pd.Series([model_name, note, test_loss, test_acc, test_precision[0], test_precision[1], test_recall[0], test_recall[1],
                        test_fscore[0], test_fscore[1], test_support[0], test_support[1], test_mcc])
    results.index = LABELS
    return results

def eval_sklearn_model(model, X_test: pd.DataFrame, y_test: list, criterion: torch.nn, device : str = None, note=None):
    '''
    Evaluate pytorch model performance on the test dataset.

    Args
    - model - sklearn model class
    - X_test - test input data
    - y_test - test labels
    - criterion - loss function
    - device - 'cpu' or 'cuda'
    - note - miscelaneous information about the evaluation

    Returns
    - a series containing model results with loss, accuracy, precision, recall, f1score, and number of samples per class 
    '''
    model_name = type(model).__name__
    out = model.predict_proba(X_test)
    
    y_prob = out[:,1]
    y_prob_tensor = torch.tensor(y_prob).float()
    y_pred = y_prob.round()
    y_test_tensor = torch.tensor(y_test).float()
    if device:
        y_prob_tensor = y_prob_tensor.to(device)
        y_test_tensor = y_test_tensor.to(device)

    test_loss = criterion(y_prob_tensor, y_test_tensor).item()
    test_acc = (y_pred == y_test).sum() / len(y_test)
    test_precision, test_recall, test_fscore, test_support = precision_recall_fscore_support(
                                                    y_true = torch.tensor(y_test),
                                                    y_pred = torch.tensor(y_pred),
                                                    zero_division=np.nan)
    test_mcc = matthews_corrcoef(y_true=y_test, y_pred=y_pred)
    
    LABELS = ['model_name', 'note', 'loss', 'acc', 'prec0', 'prec1', 'rec0', 'rec1', 'f1sc0', 'f1sc1', 'sup0', 'sup1', 'mcc']
    results = pd.Series([model_name, note, test_loss, test_acc, test_precision[0], test_precision[1], test_recall[0], test_recall[1],
                        test_fscore[0], test_fscore[1], test_support[0], test_support[1], test_mcc])
    results.index = LABELS
    return results


def append_weighted_average(metrics_df: pd.DataFrame):
    '''
    Calculates weighted averages across the folds based on the 
    number of samples of the metrics' respective classes.

    Args
    - metrics_df - a dataframe containing the fold metrics
    
    Returns
    - the modified dataframe with the new weighted average row
    '''
    metrics_df = metrics_df.copy()
    metric_names = list(metrics_df.columns[2:])
    SUP0 = 'sup0'
    SUP1 = 'sup1'

    # compute weighted averages

    weighted_avg_metrics = [metrics_df.loc[0,'model_name'], "wt_avg"]
    for metric_name in metric_names:

        # set unweighted metric values (ie loss, accuracy)

        sample_count = len(metrics_df)
        weighted_metrics = metrics_df[metric_name]

        # apply weights to base values if applicable

        if metric_name[-1] == "0":
            weighted_metrics = metrics_df[metric_name] * metrics_df[SUP0]
            sample_count = metrics_df[SUP0].sum()
        elif metric_name[-1] == "1":
            weighted_metrics = metrics_df[metric_name] * metrics_df[SUP1]
            sample_count = metrics_df[SUP1].sum()

        # calculate average

        weighted_avg = weighted_metrics.sum() / sample_count
        weighted_avg_metrics.append(weighted_avg)
    
    # create and append row to dataframe

    LABELS = ['model_name', 'note', 'loss', 'acc', 'prec0', 'prec1', 'rec0', 'rec1', 'f1sc0', 'f1sc1', 'sup0', 'sup1', 'mcc']
    weighted_avgs = pd.Series(weighted_avg_metrics).to_frame().transpose()
    weighted_avgs.columns = LABELS
    metrics_df = pd.concat([metrics_df, weighted_avgs], axis=0, ignore_index=True)
    #metrics_df = metrics_df.drop(labels=['loss'], axis=1)

    return metrics_df

def combine_several_weighted_averages(metric_dataframes: list):
    '''
    Combines the weighted averages across multiple runs into a single dataframe and calculates the mean of each metric column.

    Args
    - metric_dataframes - a list of several results dataframes

    Returns
    - a dataframe of all weighted averages and the mean of those runs
    '''
    wt_avg_list = []
    for i, df in enumerate(metric_dataframes):
        wt_avg = df[df['note'] == 'wt_avg']
        wt_avg['note'] = f'{i+1}_wt_avg'
        wt_avg_list.append(wt_avg)
    new_df = pd.concat(wt_avg_list, axis=0)

    new_df_means = new_df.iloc[-1].copy()
    new_df_means['note'] = 'wt_avg'
    for col in ['loss', 'acc', 'prec0', 'prec1', 'rec0', 'rec1', 'f1sc0', 'f1sc1', 'sup0', 'sup1', 'mcc']:
        new_df_means.loc[col] = new_df[col].mean()
    new_df = pd.concat([new_df, pd.DataFrame(new_df_means).transpose()], axis=0)
    return new_df

def create_metrics_table(metric_dataframes: list):
    '''
    Averages the class specific metrics for each model type, and aggregates
    all the final metrics in a single dataframe.

    Args
    - metric_dataframes - a list containing all the individual metric dataframes.

    Returns
    - a dataframe containing the final metrics for each model
    '''
    metrics = pd.concat(metric_dataframes, axis=0)
    metrics = metrics[metrics['note'] == "wt_avg"]

    new_metrics = metrics[['model_name', 'loss', 'acc']].copy()
    new_metrics['prec'] = (metrics.loc[:,'prec0'] + metrics.loc[:,'prec1']) / 2
    new_metrics['rec'] = (metrics.loc[:,'rec0'] + metrics.loc[:,'rec1']) / 2
    new_metrics['f1sc'] = (metrics.loc[:,'f1sc0'] + metrics.loc[:,'f1sc1']) / 2
    new_metrics = new_metrics.reset_index(drop=True)
    return new_metrics

def metric_class_averages(metric_df : pd.DataFrame):
    '''
    Creates a metric dataframe of 4 rows:

    1. Control class metrics
    2. Condition class metrics
    3. Macro average
    4. Weighted average

    Args
    - metric_df - the original metric dataframe

    Returns
    - the new reformatted dataframe
    '''

    # calculate class ratio
    support_values = metric_df[['sup0', 'sup1']].copy()
    support_ratio = (support_values['sup0'] / support_values['sup1']).item()

    def remove_end_digit(x:str):
        if len(x) == 0:
            return x
        if x[-1].isdigit():
            return x[:-1]
        return x

    # separate 0 and 1 class rows
    columns_0 = [c for c in metric_df.columns if c[-1] != '1']
    metric_0 = metric_df[columns_0].copy()
    metric_0.columns = [remove_end_digit(c) for c in metric_0.columns]
    metric_0['note'] = 0
    
    columns_1 = [c for c in metric_df.columns if c[-1] != '0']
    metric_1 = metric_df[columns_1].copy()
    metric_1.columns = [remove_end_digit(c) for c in metric_1.columns]
    metric_1['note'] = 1

    metrics_new = pd.concat([metric_0, metric_1], axis=0)

    def weighted_avg(x:pd.Series, ratio:float):
        val = x.iloc[0]
        if isinstance(val, (int, float)) == False:
            return pd.Series([val, val])
        weighted_avg = (x.iloc[0] * ratio + x.iloc[1]) / (1 + ratio)
        macro_avg = (x.iloc[0] + x.iloc[1]) / 2
        return pd.Series([macro_avg, weighted_avg])


    # calculate weighted average
    metric_avg = metrics_new.apply(weighted_avg, axis=0, args=(support_ratio,))
    metric_avg['note'] = pd.Series(['macro_avg', 'wt_avg'])
    metrics_new = pd.concat([metrics_new, metric_avg], axis=0)
    return metrics_new
    