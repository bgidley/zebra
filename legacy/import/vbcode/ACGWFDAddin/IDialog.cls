VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "IDialog"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Option Explicit
'/ stub for common dialog class
Public Property Get filter() As String
'
End Property
Public Property Get filterIndex() As Integer
'
End Property
Public Property Get dialogTitle() As String
'
End Property
Public Property Get fileName() As String
'
End Property
Public Property Let filter(filterText As String)
'
End Property
Public Property Let filterIndex(filterIndex As Integer)
'
End Property
Public Property Let dialogTitle(dialogTitle As String)
'
End Property
Public Property Let fileName(fileName As String)
'
End Property
'/ return false if save cancelled
Public Function ShowSave() As Boolean
'
End Function

