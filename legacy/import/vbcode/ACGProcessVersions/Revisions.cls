VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Revisions"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Revision 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit

Private mlngMaxRevision As Long
Private moParent As ACGContainer.Container
Private mcol As Collection
Private WithEvents moThis As ACGContainer.Container
Attribute moThis.VB_VarHelpID = -1

Friend Sub Init(oParent As Container)
    Set mcol = New Collection
    Set moThis = New ACGContainer.Container
    Set moParent = oParent
End Sub

Private Sub moThis_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub

Public Function Add(Optional ByVal oProcessDef As ProcessDef = Nothing, Optional ByVal lngRevision As Long = -1) As Revision
    Dim oNew As Revision
    Set oNew = New Revision
    If oProcessDef Is Nothing Then
        oProcessDef = New ProcessDef
    End If
    If lngRevision = -1 Then
        lngRevision = mlngMaxRevision + 1
    ElseIf lngRevision > mlngMaxRevision Then
        mlngMaxRevision = lngRevision
    End If
    oNew.Init oProcessDef, lngRevision, moThis
    mcol.Add oNew, "@" & lngRevision
    Set Add = oNew
End Function

Public Property Get MaxVer() As Long
    MaxVer = mlngMaxRevision
End Property

Public Property Get Item(RevisionId As Long) As Revision
    Set Item = mcol("@" & RevisionId)
End Property

Public Property Get Count() As Long
    Count = mcol.Count
End Property

Public Property Get ItemByPos(Index As Long) As Revision
    Set ItemByPos = mcol(Index)
End Property

Public Property Get NewEnum() As IUnknown
    'this property allows you to enumerate
    'this collection with the For...Each syntax
    Set NewEnum = mcol.[_NewEnum]
End Property

Public Property Get Version() As ProcessVersion
    Set Version = moParent.GetParent
End Property

